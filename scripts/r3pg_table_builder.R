args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript scripts/r3pg_table_builder.R input.json output.json")
}

input_path <- args[[1]]
output_path <- args[[2]]

required_packages <- c("jsonlite", "r3PG")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  stop(paste("Missing required R packages:", paste(missing_packages, collapse = ", ")))
}

payload <- jsonlite::read_json(input_path, simplifyVector = FALSE)
params <- payload$parameters
if (is.null(params)) {
  params <- list()
}

normalize_species <- function(value) {
  if (is.null(value) || value == "") {
    return("Fagus sylvatica")
  }
  lookup <- list(
    "European beech" = "Fagus sylvatica",
    "beech" = "Fagus sylvatica",
    "buche" = "Fagus sylvatica",
    "Fagus sylvatica" = "Fagus sylvatica",
    "Douglas fir" = "Pseudotsuga menziesii",
    "douglas fir" = "Pseudotsuga menziesii",
    "douglasie" = "Pseudotsuga menziesii",
    "Pseudotsuga menziesii" = "Pseudotsuga menziesii",
    "fir" = "Abies alba",
    "silver fir" = "Abies alba",
    "tanne" = "Abies alba",
    "Abies alba" = "Abies alba",
    "larch" = "Larix decidua",
    "laerche" = "Larix decidua",
    "lärche" = "Larix decidua",
    "Larix decidua" = "Larix decidua",
    "oak" = "Quercus robur",
    "eiche" = "Quercus robur",
    "Quercus robur" = "Quercus robur",
    "pine" = "Pinus sylvestris",
    "Scots pine" = "Pinus sylvestris",
    "scots pine" = "Pinus sylvestris",
    "kiefer" = "Pinus sylvestris",
    "Pinus sylvestris" = "Pinus sylvestris",
    "Norway spruce" = "Picea abies",
    "norway spruce" = "Picea abies",
    "spruce" = "Picea abies",
    "Picea abies" = "Picea abies"
  )
  if (!is.null(lookup[[value]])) {
    return(lookup[[value]])
  }
  value
}

value_or <- function(value, default) {
  if (is.null(value)) {
    return(default)
  }
  value
}

planted_value <- function(entry, start_year) {
  if (!is.null(entry$planted) && entry$planted != "") {
    planted <- as.character(entry$planted)
    if (grepl("^\\d{4}$", planted)) {
      return(sprintf("%s-01", planted))
    }
    return(planted)
  }
  if (!is.null(entry$planted_year) && entry$planted_year != "") {
    return(sprintf("%04d-01", as.integer(entry$planted_year)))
  }
  planted_year <- start_year - as.integer(value_or(entry$initial_age_years, 40))
  sprintf("%04d-01", planted_year)
}

select_parameter_set <- function(overview, params, species_name) {
  if (!is.null(params$parameter_set_id)) {
    selected <- overview[overview$parset_id == as.integer(params$parameter_set_id), , drop = FALSE]
    if (nrow(selected) == 0) {
      stop(paste("parameter_set_id not available for species:", params$parameter_set_id))
    }
    return(selected[1, , drop = FALSE])
  }

  is_mixed <- !is.null(params$species_entries) && length(params$species_entries) > 1
  preferred_parameter_sets <- list(
    "Picea abies" = 37,
    "Larix decidua" = 36,
    "Fagus sylvatica" = 29
  )
  if (!is.null(preferred_parameter_sets[[species_name]])) {
    selected <- overview[overview$parset_id == preferred_parameter_sets[[species_name]], , drop = FALSE]
    if (nrow(selected) > 0) {
      return(selected[1, , drop = FALSE])
    }
  }

  candidates <- overview
  if (!is.null(params$stand_age_type)) {
    filtered <- candidates[candidates$age == params$stand_age_type, , drop = FALSE]
    if (nrow(filtered) > 0) {
      candidates <- filtered
    }
  } else {
    default_age <- if (is_mixed) "uneven" else "even"
    filtered <- candidates[candidates$age == default_age, , drop = FALSE]
    if (nrow(filtered) > 0) {
      candidates <- filtered
    }
  }

  if (!is.null(params$stand_type)) {
    filtered <- candidates[candidates$type == params$stand_type, , drop = FALSE]
    if (nrow(filtered) > 0) {
      candidates <- filtered
    }
  } else {
    default_type <- if (is_mixed) "mixed" else "mono"
    filtered <- candidates[candidates$type == default_type, , drop = FALSE]
    if (nrow(filtered) > 0) {
      candidates <- filtered
    }
  }

  usable_candidates <- candidates[vapply(
    candidates$parset_id,
    function(parset_id) has_usable_size_distribution(candidates$species[1], parset_id),
    logical(1)
  ), , drop = FALSE]
  if (nrow(usable_candidates) > 0) {
    return(usable_candidates[1, , drop = FALSE])
  }

  usable_overview <- overview[vapply(
    overview$parset_id,
    function(parset_id) has_usable_size_distribution(overview$species[1], parset_id),
    logical(1)
  ), , drop = FALSE]
  if (nrow(usable_overview) > 0) {
    return(usable_overview[1, , drop = FALSE])
  }

  candidates[1, , drop = FALSE]
}

select_parameter_table <- function(table, column, output_column) {
  if (!column %in% names(table)) {
    stop(paste("Parameter column not found:", column))
  }
  selected <- table[, c("parameter", column), drop = FALSE]
  names(selected)[2] <- output_column
  selected
}

select_size_distribution_table <- function(species_name, preferred_column) {
  size_table <- r3PG::get_parameters(mode = "sizeDist", sp_names = species_name)
  column <- preferred_column

  if (!column %in% names(size_table) || all(is.na(size_table[[column]]))) {
    candidate_columns <- setdiff(names(size_table), "parameter")
    usable <- candidate_columns[!vapply(candidate_columns, function(name) all(is.na(size_table[[name]])), logical(1))]
    if (length(usable) > 0) {
      column <- usable[[1]]
    } else if (species_name %in% names(r3PG::d_sizeDist)) {
      selected <- r3PG::d_sizeDist[, c("parameter", species_name), drop = FALSE]
      return(selected)
    } else {
      selected <- data.frame(parameter = size_table$parameter, value = 0)
      names(selected)[2] <- species_name
      return(selected)
    }
  }

  select_parameter_table(size_table, column, species_name)
}

make_cohort_labels <- function(entries, base_names) {
  counts <- table(base_names)
  seen <- list()
  labels <- character(length(base_names))

  for (i in seq_along(base_names)) {
    base_name <- base_names[[i]]
    seen[[base_name]] <- value_or(seen[[base_name]], 0) + 1
    entry <- entries[[i]]
    explicit_label <- value_or(entry$cohort_label, entry$cohort_id)

    if (!is.null(explicit_label) && explicit_label != "") {
      labels[[i]] <- paste(base_name, explicit_label, sep = " | ")
    } else if (counts[[base_name]] > 1) {
      labels[[i]] <- paste(base_name, paste("cohort", seen[[base_name]]), sep = " | ")
    } else {
      labels[[i]] <- base_name
    }
  }

  labels
}

has_usable_size_distribution <- function(species_name, parset_id) {
  size_table <- r3PG::get_parameters(mode = "sizeDist", sp_names = species_name)
  column <- paste(species_name, parset_id)
  column %in% names(size_table) && !all(is.na(size_table[[column]]))
}

species_entries <- params$species_entries
if (is.null(species_entries) || length(species_entries) == 0) {
  species_entries <- list(params)
}
species_base_names <- vapply(species_entries, function(entry) normalize_species(entry$species), character(1))
species_names <- make_cohort_labels(species_entries, species_base_names)
selected_overviews <- list()
parameter_columns <- character()
for (i in seq_along(species_names)) {
  species_name <- species_base_names[[i]]
  overview <- r3PG::get_parameters(mode = "overview", sp_names = species_name)
  if (nrow(overview) == 0) {
    # Try a permissive fallback: search available overview species for partial matches
    all_overview <- r3PG::get_parameters(mode = "overview")
    # build tokens from requested name (e.g. "Fagus sylvatica" -> c("fagus","sylvatica"))
    tokens <- unlist(strsplit(tolower(species_name), "\\s+"))
    match_idx <- integer()
    for (t in tokens) {
      if (nchar(t) == 0) next
      match_idx <- unique(c(match_idx, which(grepl(t, tolower(all_overview$species)))))
    }
    # also try some common name tokens if no token match found
    if (length(match_idx) == 0) {
      common_tokens <- c("beech", "buche", "fagus", "spruce", "picea", "larix", "larch", "pine", "pinus")
      for (t in common_tokens) {
        match_idx <- unique(c(match_idx, which(grepl(t, tolower(all_overview$species)))))
        if (length(match_idx) > 0) break
      }
    }
    if (length(match_idx) > 0) {
      # pick the first sensible candidate and re-query overview for that name
      candidate <- all_overview$species[match_idx[1]]
      message(sprintf("r3PG overview: no direct match for '%s'; falling back to available '%s'", species_name, candidate))
      species_name <- candidate
      species_base_names[[i]] <- species_name
      overview <- r3PG::get_parameters(mode = "overview", sp_names = species_name)
    } else {
      stop(paste(
        "No r3PG parameter set for species:",
        species_name,
        "Available:",
        paste(unique(all_overview$species), collapse = ", ")
      ))
    }
  }
  selected_overview <- select_parameter_set(overview, params, species_name)
  selected_overviews[[i]] <- selected_overview
  parameter_columns[[i]] <- paste(selected_overview$species, selected_overview$parset_id)
}

start_year <- as.integer(value_or(params$start_year, 2026))
horizon_years <- as.integer(value_or(params$horizon_years, 20))
end_year <- start_year + horizon_years - 1

site <- r3PG::d_site[1, , drop = FALSE]
site$latitude <- as.numeric(value_or(params$latitude, site$latitude[1]))
site$altitude <- as.numeric(value_or(params$altitude, site$altitude[1]))
site$soil_class <- as.integer(value_or(params$soil_class, site$soil_class[1]))
site$asw_i <- as.numeric(value_or(params$soil_water_initial_mm, site$asw_i[1]))
site$asw_min <- as.numeric(value_or(params$soil_water_min_mm, site$asw_min[1]))
site$asw_max <- as.numeric(value_or(params$soil_water_capacity_mm, site$asw_max[1]))
site$from <- sprintf("%04d-01", start_year)
site$to <- sprintf("%04d-12", end_year)

species_rows <- list()
for (i in seq_along(species_entries)) {
  entry <- species_entries[[i]]
  species_name <- species_names[[i]]
  species_base_name <- species_base_names[[i]]
  row <- r3PG::d_species[r3PG::d_species$species == species_base_name, , drop = FALSE]
  if (nrow(row) == 0) {
    row <- r3PG::d_species[1, , drop = FALSE]
  }
  row$species <- species_name
  row$planted <- planted_value(entry, start_year)
  row$fertility <- as.numeric(value_or(params$site_fertility, row$fertility[1]))
  row$stems_n <- as.numeric(value_or(entry$initial_stems_per_ha, row$stems_n[1]))
  row$biom_stem <- as.numeric(value_or(entry$initial_stem_biomass_t_ha, row$biom_stem[1]))
  row$biom_root <- as.numeric(value_or(entry$initial_root_biomass_t_ha, row$biom_root[1]))
  row$biom_foliage <- as.numeric(value_or(entry$initial_foliage_biomass_t_ha, row$biom_foliage[1]))
  species_rows[[i]] <- row
}
species <- do.call(rbind, species_rows)

climate <- r3PG::d_climate
climate_years <- sort(unique(climate$year))
template <- climate[climate$year %in% climate_years[seq_len(min(length(climate_years), horizon_years))], ]
if (nrow(template) == 0) {
  template <- climate
}
copies <- ceiling((horizon_years * 12) / nrow(template))
climate <- do.call(rbind, replicate(copies, template, simplify = FALSE))
climate <- climate[seq_len(horizon_years * 12), ]
climate$year <- rep(start_year:end_year, each = 12)
climate$month <- rep(1:12, times = horizon_years)

thinning <- data.frame(
  species = character(),
  age = numeric(),
  stems_n = numeric(),
  stem = numeric(),
  root = numeric(),
  foliage = numeric(),
  stringsAsFactors = FALSE
)
dynamic_thinning <- list()
schedule <- params$thinning_schedule
if (!is.null(schedule) && length(schedule) > 0) {
  schedule <- schedule[order(vapply(schedule, function(thin) as.numeric(thin$year), numeric(1)))]
  for (thin in schedule) {
    thin_species_base <- normalize_species(value_or(thin$species, species_base_names[1]))
    matching_indices <- which(species_base_names == thin_species_base)
    if (!is.null(thin$cohort_label) || !is.null(thin$cohort_id)) {
      thin_label <- paste(thin_species_base, value_or(thin$cohort_label, thin$cohort_id), sep = " | ")
      matching_indices <- which(species_names == thin_label)
    }
    if (length(matching_indices) == 0) {
      next
    }
    year_offset <- as.integer(value_or(thin$year, 1))
    removal_fraction <- as.numeric(value_or(thin$removal_fraction, 0))
    for (matching_index in matching_indices) {
      entry <- species_entries[[matching_index]]
      dynamic_thinning[[length(dynamic_thinning) + 1]] <- list(
        species = species_names[[matching_index]],
        age = as.integer(value_or(entry$initial_age_years, 40)) + year_offset,
        year_offset = year_offset,
        removal_fraction = removal_fraction
      )
    }
  }
}

parameter_tables <- list()
size_dist_tables <- list()
for (i in seq_along(species_names)) {
  species_name <- species_names[[i]]
  species_base_name <- species_base_names[[i]]
  parameter_tables[[i]] <- select_parameter_table(
    table = r3PG::get_parameters(mode = "parameters", sp_names = species_base_name),
    column = parameter_columns[[i]],
    output_column = species_name
  )
  size_dist_table <- select_size_distribution_table(
    species_name = species_base_name,
    preferred_column = parameter_columns[[i]]
  )
  names(size_dist_table)[2] <- species_name
  size_dist_tables[[i]] <- size_dist_table
}
parameters <- Reduce(function(left, right) merge(left, right, by = "parameter", all = TRUE), parameter_tables)
size_dist <- Reduce(function(left, right) merge(left, right, by = "parameter", all = TRUE), size_dist_tables)
set_parameter <- function(species_name, name, value) {
  parameters[parameters$parameter == name, species_name] <<- value
}
for (i in seq_along(species_names)) {
  species_name <- species_names[[i]]
  species_base_name <- species_base_names[[i]]
  if (species_base_name == "Picea abies") {
    set_parameter(species_name, "gammaN0", 0.2)
    set_parameter(species_name, "gammaN1", 1.0)
    set_parameter(species_name, "tgammaN", 80)
    set_parameter(species_name, "ngammaN", 2)
  }
  if (species_base_name == "Larix decidua") {
    set_parameter(species_name, "gammaN0", 0.2)
    set_parameter(species_name, "gammaN1", 1.0)
    set_parameter(species_name, "tgammaN", 80)
    set_parameter(species_name, "ngammaN", 2)
  }
  if (species_base_name == "Fagus sylvatica") {
    set_parameter(species_name, "gammaN0", 0.1)
    set_parameter(species_name, "gammaN1", 0.6)
    set_parameter(species_name, "tgammaN", 100)
    set_parameter(species_name, "ngammaN", 2)
  }
}

settings <- list(
  light_model = 2,
  transp_model = 2,
  phys_model = 2,
  height_model = 2,
  correct_bias = 1,
  calculate_d13c = 0
)
if (!is.null(params$settings)) {
  settings <- modifyList(settings, params$settings)
}

jsonlite::write_json(
  list(
    site = site,
    species = species,
    climate = climate,
    thinning = thinning,
    parameters = parameters,
    size_dist = size_dist,
    settings = settings,
    metadata = list(
      species = species_names,
      base_species = species_base_names,
      parameter_sets = lapply(selected_overviews, function(item) as.list(item[1, , drop = TRUE])),
      dynamic_thinning = dynamic_thinning,
      start_year = start_year,
      horizon_years = horizon_years,
      source = "Built from simplified ForestGPT input using r3PG::get_parameters defaults."
    )
  ),
  output_path,
  auto_unbox = TRUE,
  dataframe = "rows",
  null = "null"
)
