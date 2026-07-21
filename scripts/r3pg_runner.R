args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript scripts/r3pg_runner.R input.json output.json")
}

input_path <- args[[1]]
output_path <- args[[2]]

required_packages <- c("jsonlite", "r3PG")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  stop(paste("Missing required R packages:", paste(missing_packages, collapse = ", ")))
}

payload <- jsonlite::read_json(input_path, simplifyVector = TRUE)
raw_inputs <- payload$raw_inputs

as_table <- function(value) {
  if (is.null(value)) {
    return(NULL)
  }
  if (is.data.frame(value)) {
    return(coerce_numeric_columns(value))
  }
  if (is.list(value) && length(value) == 0) {
    return(NULL)
  }
  coerce_numeric_columns(as.data.frame(value, stringsAsFactors = FALSE))
}

coerce_numeric_columns <- function(table) {
  for (column in names(table)) {
    if (is.integer(table[[column]])) {
      table[[column]] <- as.numeric(table[[column]])
    }
  }
  table
}

site <- as_table(raw_inputs$site)
species <- as_table(raw_inputs$species)
climate <- as_table(raw_inputs$climate)
thinning <- as_table(raw_inputs$thinning)
parameters <- as_table(raw_inputs$parameters)
size_dist <- as_table(raw_inputs$size_dist)
settings <- raw_inputs$settings

if (is.null(settings)) {
  settings <- list(
    light_model = 2,
    transp_model = 2,
    phys_model = 2,
    height_model = 1,
    correct_bias = 0,
    calculate_d13c = 0
  )
}

run_model <- function(
  thinning_table,
  species_table = species,
  parameters_table = parameters,
  size_dist_table = size_dist
) {
  r3PG::run_3PG(
    site = site,
    species = species_table,
    climate = climate,
    thinning = thinning_table,
    parameters = parameters_table,
    size_dist = size_dist_table,
    settings = settings,
    check_input = TRUE,
    df_out = TRUE
  )
}

resolved_thinning <- list()
dynamic_thinning <- raw_inputs$metadata$dynamic_thinning
if (!is.null(dynamic_thinning) && length(dynamic_thinning) > 0) {
  if (is.data.frame(dynamic_thinning)) {
    dynamic_thinning <- split(dynamic_thinning, seq_len(nrow(dynamic_thinning)))
  }
  baseline_records <- as.data.frame(run_model(NULL), stringsAsFactors = FALSE)
  for (thin in dynamic_thinning) {
    thin_species <- thin$species
    thin_age <- as.numeric(thin$age)
    removal_fraction <- as.numeric(thin$removal_fraction)
    rows <- baseline_records[
      baseline_records$species == thin_species &
        baseline_records$variable == "stems_n",
    ]
    if (nrow(rows) == 0) {
      next
    }
    rows$age_value <- NA_real_
    age_rows <- baseline_records[
      baseline_records$species == thin_species &
        baseline_records$variable == "age",
    ]
    if (nrow(age_rows) > 0) {
      rows$age_value <- as.numeric(age_rows$value[match(rows$date, age_rows$date)])
    }
    candidates <- rows[!is.na(rows$age_value) & rows$age_value >= thin_age, ]
    if (nrow(candidates) == 0) {
      candidates <- rows[nrow(rows), , drop = FALSE]
    }
    current_stems <- as.numeric(candidates$value[[1]])
    target_stems <- current_stems * (1 - removal_fraction)
    thinning <- rbind(thinning, data.frame(
      species = thin_species,
      age = thin_age,
      stems_n = target_stems,
      stem = 1,
      root = 1,
      foliage = 1,
      stringsAsFactors = FALSE
    ))
    resolved_thinning[[length(resolved_thinning) + 1]] <- list(
      species = thin_species,
      age = thin_age,
      removal_fraction = removal_fraction,
      stems_before = current_stems,
      stems_after = target_stems
    )
  }
}

out <- run_model(thinning)

records <- as.data.frame(out, stringsAsFactors = FALSE)
if ("date" %in% names(records)) {
  records$year <- as.integer(format(as.Date(records$date), "%Y"))
}
fallback_cohort_runs <- list()
if ("species" %in% names(records) && "species" %in% names(species)) {
  planted_year_lookup <- setNames(as.integer(substr(species$planted, 1, 4)), species$species)
  missing_species <- species$species[!vapply(species$species, function(species_name) {
    planted_year <- planted_year_lookup[[species_name]]
    species_records <- records[records$species == species_name, , drop = FALSE]
    if (nrow(species_records) == 0) {
      return(FALSE)
    }
    if ("year" %in% names(species_records) && !is.null(planted_year) && !is.na(planted_year)) {
      post_planting_records <- species_records[species_records$year >= planted_year, , drop = FALSE]
      if (nrow(post_planting_records) == 0) {
        return(FALSE)
      }
      if (all(c("variable", "value") %in% names(post_planting_records))) {
        active_records <- post_planting_records[
          post_planting_records$variable %in% c("stems_n", "biom_stem", "biom_root", "biom_foliage", "basal_area", "volume") &
            !is.na(as.numeric(post_planting_records$value)) &
            as.numeric(post_planting_records$value) > 0,
          ,
          drop = FALSE
        ]
        return(nrow(active_records) > 0)
      }
      return(TRUE)
    }
    TRUE
  }, logical(1))]
  for (missing_name in missing_species) {
    if (!missing_name %in% names(parameters)) {
      next
    }
    single_species <- species[species$species == missing_name, , drop = FALSE]
    single_parameters <- parameters[, c("parameter", missing_name), drop = FALSE]
    single_size_dist <- NULL
    if (!is.null(size_dist) && missing_name %in% names(size_dist)) {
      single_size_dist <- size_dist[, c("parameter", missing_name), drop = FALSE]
    }
    single_thinning <- thinning
    if (!is.null(single_thinning) && nrow(single_thinning) > 0 && "species" %in% names(single_thinning)) {
      single_thinning <- single_thinning[single_thinning$species == missing_name, , drop = FALSE]
    }
    single_out <- tryCatch(
      run_model(
        thinning_table = single_thinning,
        species_table = single_species,
        parameters_table = single_parameters,
        size_dist_table = single_size_dist
      ),
      error = function(error) NULL
    )
    if (!is.null(single_out)) {
      single_records <- as.data.frame(single_out, stringsAsFactors = FALSE)
      if (nrow(single_records) > 0 && "species" %in% names(single_records)) {
        records <- rbind(records, single_records)
        fallback_cohort_runs[[length(fallback_cohort_runs) + 1]] <- list(
          species = missing_name,
          note = "Species/cohort was omitted by the combined r3PG run and was rerun separately."
        )
      }
    }
  }
}
annual_outputs <- list()
annual_diagnostics <- list()

if (all(c("date", "variable", "value") %in% names(records))) {
  records$year <- as.integer(format(as.Date(records$date), "%Y"))
  years <- sort(unique(records$year))
  species_names <- sort(unique(records$species))
  planted_years <- setNames(as.integer(substr(species$planted, 1, 4)), species$species)
  for (year in years) {
    for (species_name in species_names) {
    planted_year <- planted_years[[species_name]]
    if (!is.null(planted_year) && !is.na(planted_year) && year < planted_year) {
      next
    }
    year_rows <- records[records$year == year & records$species == species_name, ]

    get_value <- function(variable_names) {
      for (variable_name in variable_names) {
        variable_rows <- year_rows[year_rows$variable == variable_name, ]
        if (nrow(variable_rows) > 0) {
          values <- variable_rows$value
          values <- values[!is.na(values)]
          if (length(values) > 0) {
            return(as.numeric(values[[length(values)]]))
          }
        }
      }
      0
    }
    get_stat <- function(variable_name, stat = "last") {
      variable_rows <- year_rows[year_rows$variable == variable_name, ]
      if (nrow(variable_rows) == 0) {
        return(0)
      }
      values <- as.numeric(variable_rows$value)
      values <- values[!is.na(values)]
      if (length(values) == 0) {
        return(0)
      }
      if (stat == "max") {
        return(max(values))
      }
      if (stat == "mean") {
        return(mean(values))
      }
      if (stat == "sum") {
        return(sum(values))
      }
      if (stat == "first") {
        return(as.numeric(values[[1]]))
      }
      as.numeric(values[[length(values)]])
    }

    annual_outputs[[length(annual_outputs) + 1]] <- list(
      year = as.integer(year),
      species = species_name,
      age_years = as.integer(get_value(c("age"))),
      stems_per_ha = get_value(c("stems_n", "stems", "N")),
      basal_area_m2_ha = get_value(c("basal_area", "ba")),
      mean_dbh_cm = get_value(c("dbh")),
      mean_height_m = get_value(c("height")),
      standing_volume_m3_ha = get_value(c("volume", "vol_stem", "V")),
      aboveground_biomass_t_ha = get_value(c("biom_stem")) + get_value(c("biom_foliage")),
      mean_annual_increment_m3_ha_yr = get_value(c("volume_mai")),
      canopy_cover = get_stat("canopy_cover", "last"),
      canopy_cover_max = get_stat("canopy_cover", "max"),
      canopy_volume_fraction = get_stat("canopy_vol_frac", "last"),
      canopy_volume_fraction_max = get_stat("canopy_vol_frac", "max"),
      notes = list("Normalized from r3PG monthly long-format output.")
    )

    annual_diagnostics[[length(annual_diagnostics) + 1]] <- list(
      year = as.integer(year),
      species = species_name,
      stems_start = get_stat("stems_n", "first"),
      stems_end = get_stat("stems_n", "last"),
      mort_stress_sum = get_stat("mort_stress", "sum"),
      mort_thinn_sum = get_stat("mort_thinn", "sum"),
      gamma_n_mean = get_stat("gammaN", "mean"),
      biom_tree = get_stat("biom_tree", "last"),
      biom_tree_max = get_stat("biom_tree_max", "last"),
      basal_area = get_stat("basal_area", "last"),
      lai_max = get_stat("lai", "max"),
      lai_mean = get_stat("lai", "mean"),
      canopy_cover_max = get_stat("canopy_cover", "max"),
      canopy_volume_fraction = get_stat("canopy_vol_frac", "last"),
      canopy_volume_fraction_max = get_stat("canopy_vol_frac", "max")
    )
    }
  }
}

summary <- list(
  raw_row_count = nrow(records),
  annual_output_count = length(annual_outputs),
  diagnostics = annual_diagnostics,
  resolved_thinning = resolved_thinning,
  fallback_cohort_runs = fallback_cohort_runs,
  variables = if ("variable" %in% names(records)) unique(records$variable) else list()
)

jsonlite::write_json(
  list(
    model_version = as.character(utils::packageVersion("r3PG")),
    summary = summary,
    annual_outputs = annual_outputs,
    raw_records = head(records, 5000)
  ),
  output_path,
  auto_unbox = TRUE,
  null = "null"
)
