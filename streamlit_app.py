import os

import altair as alt
import pandas as pd
import requests
import streamlit as st


st.set_page_config(page_title="ForestGPT Dev", layout="wide")
st.title("ForestGPT Dev Dashboard")

api = st.sidebar.text_input(
    "API URL",
    os.getenv("FORESTGPT_API_URL", "http://127.0.0.1:8003"),
)

try:
    health = requests.get(f"{api}/health", timeout=2)
    if health.status_code == 200 and health.headers.get("content-type", "").startswith("application/json"):
        st.sidebar.success("FastAPI connected")
    else:
        st.sidebar.error("API URL is not FastAPI. Check the port.")
except Exception as exc:
    st.sidebar.error(f"FastAPI not reachable: {exc}")


def post(path, payload, show_json=True):
    response = requests.post(f"{api}{path}", json=payload, timeout=60)
    st.caption(f"HTTP {response.status_code}")
    try:
        data = response.json()
        if show_json:
            st.json(data)
        return data
    except Exception:
        st.text(response.text)
        return None


def normalize_species_name(value):
    aliases = {
        "spruce": "Picea abies",
        "norway spruce": "Picea abies",
        "picea abies": "Picea abies",
        "larch": "Larix decidua",
        "laerche": "Larix decidua",
        "lärche": "Larix decidua",
        "larix decidua": "Larix decidua",
        "beech": "Fagus sylvatica",
        "buche": "Fagus sylvatica",
        "european beech": "Fagus sylvatica",
        "fagus sylvatica": "Fagus sylvatica",
    }
    return aliases.get(str(value).lower(), value)


def growth_chart(data, field, title, unit, species_colors):
    return (
        alt.Chart(data)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("Year:Q", title="Year", axis=alt.Axis(format="d")),
            y=alt.Y(f"{field}:Q", title=unit, scale=alt.Scale(zero=False)),
            color=alt.Color(
                "Species:N",
                scale=alt.Scale(domain=list(species_colors), range=list(species_colors.values())),
                legend=alt.Legend(title="Species"),
            ),
            tooltip=[
                alt.Tooltip("Year:Q", format="d"),
                alt.Tooltip("Species:N"),
                alt.Tooltip(f"{field}:Q", title=unit, format=".2f"),
            ],
        )
        .properties(title=title, height=220)
    )


def total_growth_chart(data, field, title, unit):
    return (
        alt.Chart(data)
        .mark_line(point=True, strokeWidth=2, color="#284f73")
        .encode(
            x=alt.X("Year:Q", title="Year", axis=alt.Axis(format="d")),
            y=alt.Y(f"{field}:Q", title=unit, scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("Year:Q", format="d"),
                alt.Tooltip(f"{field}:Q", title=unit, format=".2f"),
            ],
        )
        .properties(title=title, height=220)
    )


def total_by_year(data, source_field, target_field):
    return (
        data.dropna(subset=[source_field])
        .groupby("Year", as_index=False)[source_field]
        .sum()
        .rename(columns={source_field: target_field})
    )


def base_species_label(species_label):
    return str(species_label).split("|", 1)[0].strip()


def chart_colors(species_labels):
    palette = [
        "#2f6b45",
        "#bd7b21",
        "#9b3f35",
        "#3568a8",
        "#6f4a8e",
        "#4f8f8b",
        "#b45f06",
        "#5f6f2a",
        "#8a4f3d",
    ]
    base_species = []
    for species in species_labels:
        base_name = base_species_label(species)
        if base_name not in base_species:
            base_species.append(base_name)
    base_colors = {species: palette[index % len(palette)] for index, species in enumerate(base_species)}
    return {species: base_colors[base_species_label(species)] for species in species_labels}


MAX_SPECIES_ROWS = 9
MAX_THINNING_ROWS = 9


def clear_simulation_setup():
    prefixes = (
        "species_name_",
        "cohort_label_",
        "yield_table_",
        "species_age_",
        "species_top_height_",
        "species_stocking_degree_",
        "species_share_",
        "species_stems_",
        "species_mean_height_",
        "species_mean_dbh_",
        "thinning_species_",
        "thinning_cohort_",
        "thinning_year_",
        "thinning_percent_",
    )
    exact_keys = {
        "simulation_stand_id",
        "simulation_altitude",
        "simulation_soil_moisture",
        "simulation_site_fertility",
        "simulation_horizon",
        "show_growth_plots",
        "simulation_table",
        "thinning_ages",
        "simulation_diagnostics",
        "diagnostic_table",
        "show_plots",
    }
    for key in list(st.session_state):
        if key in exact_keys or key.startswith(prefixes):
            del st.session_state[key]


def row_header(columns, labels):
    for column, label in zip(columns, labels):
        column.markdown(f"<small><b>{label}</b></small>", unsafe_allow_html=True)


def output_species_labels(rows):
    canonical_counts = {}
    for row in rows:
        if row["active"]:
            canonical_counts[row["canonical"]] = canonical_counts.get(row["canonical"], 0) + 1

    seen = {}
    labels = []
    for row in rows:
        if not row["active"]:
            labels.append("")
            continue
        canonical = row["canonical"]
        seen[canonical] = seen.get(canonical, 0) + 1
        if row["cohort_label"]:
            labels.append(f"{canonical} | {row['cohort_label']}")
        elif canonical_counts[canonical] > 1:
            labels.append(f"{canonical} | cohort {seen[canonical]}")
        else:
            labels.append(canonical)
    return labels


st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlock"] { gap: 0.35rem; }
    div[data-testid="column"] { padding-left: 0.15rem; padding-right: 0.15rem; }
    div[data-testid="stNumberInput"] label,
    div[data-testid="stTextInput"] label,
    div[data-testid="stSelectbox"] label { margin-bottom: 0.05rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.expander("Simulation setup", expanded=True):
    if st.button("Clear simulation setup", type="secondary"):
        clear_simulation_setup()
        st.rerun()

    for index in range(1, MAX_SPECIES_ROWS + 1):
        st.session_state[f"thinning_species_{index}"] = st.session_state.get(f"species_name_{index}", "")
        st.session_state[f"thinning_cohort_{index}"] = st.session_state.get(f"cohort_label_{index}", "")

    st.subheader("Stand")
    c1, c2, c3, c4 = st.columns(4)
    stand_id = c1.number_input("Stand ID", min_value=1, value=None, key="simulation_stand_id")
    altitude = c2.number_input("Altitude m", value=None, key="simulation_altitude")
    soil_moisture = c3.selectbox(
        "Soil moisture",
        [None, "dry", "mesic", "moist", "wet"],
        format_func=lambda value: "" if value is None else value,
        key="simulation_soil_moisture",
    )
    site_fertility = c4.number_input("Site fertility", min_value=0.0, max_value=1.0, value=None, key="simulation_site_fertility")

    st.subheader("Species")
    species_entries = []
    species_rows = []
    stand_stocking_degree = None
    species_header = st.columns([0.35, 1.05, 0.75, 1.1, 0.55, 0.65, 0.7, 0.55, 0.7, 0.7, 0.75])
    row_header(species_header, ["", "Species", "Cohort", "Yield table", "Age", "Top H", "Stock", "Share", "N/ha", "H", "DBH"])
    for index in range(1, MAX_SPECIES_ROWS + 1):
        species_default, cohort_default, table_default = "", "", ""
        c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = st.columns(
            [0.35, 1.05, 0.75, 1.1, 0.55, 0.65, 0.7, 0.55, 0.7, 0.7, 0.75]
        )
        c0.caption(str(index))
        species_name = c1.text_input("Species", species_default, key=f"species_name_{index}", label_visibility="collapsed")
        cohort_label = c2.text_input("Cohort", cohort_default, key=f"cohort_label_{index}", label_visibility="collapsed")
        yield_table_id = c3.text_input("Yield table", table_default, key=f"yield_table_{index}", label_visibility="collapsed")
        age = c4.number_input("Age", min_value=0, value=None, key=f"species_age_{index}", label_visibility="collapsed")
        top_height = c5.number_input(
            "Top height m",
            min_value=0.0,
            value=None,
            key=f"species_top_height_{index}",
            label_visibility="collapsed",
        )
        if index == 1:
            stand_stocking_degree = c6.number_input(
                "Stocking degree",
                min_value=0.0,
                max_value=1.0,
                value=None,
                key="species_stocking_degree_1",
                label_visibility="collapsed",
            )
        else:
            c6.caption("")
        share = c7.number_input("Share", min_value=0.0, max_value=1.0, value=None, key=f"species_share_{index}", label_visibility="collapsed")
        stems = c8.number_input("Stems/ha", min_value=1, value=None, key=f"species_stems_{index}", label_visibility="collapsed")
        mean_height = c9.number_input("Mean height m", min_value=0.0, value=None, key=f"species_mean_height_{index}", label_visibility="collapsed")
        mean_dbh = c10.number_input("Mean diameter cm", min_value=0.0, value=None, key=f"species_mean_dbh_{index}", label_visibility="collapsed")
        entry = {
            "species": species_name,
            "cohort_label": cohort_label,
            "age_years": age,
            "top_height_m": top_height,
            "stocking_degree": stand_stocking_degree,
            "share": share,
            "stems_per_ha": stems,
            "mean_height_m": mean_height,
            "mean_dbh_cm": mean_dbh,
        }
        if top_height is not None and not all(value is not None for value in (stems, mean_height, mean_dbh)):
            entry["yield_table_id"] = yield_table_id
        entry = {key: value for key, value in entry.items() if value is not None and value != ""}
        is_active = bool(species_name.strip()) and any(value is not None for value in (age, top_height, stems, mean_height, mean_dbh))
        if is_active:
            species_entries.append(entry)
        species_rows.append(
            {
                "row": index,
                "name": species_name,
                "canonical": normalize_species_name(species_name),
                "cohort_label": cohort_label.strip(),
                "age": age,
                "active": is_active,
            }
        )

    st.subheader("Thinning")
    st.caption("Thinning intensity is the percentage of stems removed. r3PG receives the resulting number of trees remaining.")
    thinning_errors = []
    thinning_schedule = []
    active_species_rows = [row for row in species_rows if row["active"]]
    active_output_labels = output_species_labels(active_species_rows)
    for row, output_label in zip(active_species_rows, active_output_labels):
        row["output_label"] = output_label

    thinning_widths = [0.95, 0.65, 0.55, 0.68, 0.55, 0.68, 0.55, 0.68, 0.55, 0.68]
    thinning_header = st.columns(thinning_widths)
    row_header(
        thinning_header,
        ["Species", "Cohort", "Yr 1", "Rem. 1", "Yr 2", "Rem. 2", "Yr 3", "Rem. 3", "Yr 4", "Rem. 4"],
    )
    year_columns = st.columns(thinning_widths)
    year_columns[0].caption("")
    year_columns[1].caption("")
    thinning_years = []
    for index in range(1, 5):
        year_column = year_columns[2 + ((index - 1) * 2)]
        removal_column = year_columns[3 + ((index - 1) * 2)]
        thinning_years.append(
            year_column.number_input(
                f"Year {index}. thinning",
                min_value=1,
                value=None,
                key=f"thinning_year_{index}",
                label_visibility="collapsed",
            )
        )
        removal_column.caption("%")

    active_targets = {
        (str(row["canonical"]).lower(), row["cohort_label"].lower()): row
        for row in species_rows
        if row["active"]
    }
    for species_index in range(1, MAX_THINNING_ROWS + 1):
        percent_columns = st.columns(thinning_widths)
        thinning_species = percent_columns[0].text_input(
            f"Thinning species {species_index}",
            "",
            key=f"thinning_species_{species_index}",
            label_visibility="collapsed",
            disabled=True,
        )
        thinning_cohort = percent_columns[1].text_input(
            f"Thinning cohort {species_index}",
            "",
            key=f"thinning_cohort_{species_index}",
            label_visibility="collapsed",
            disabled=True,
        )
        target_key = (str(normalize_species_name(thinning_species)).lower(), thinning_cohort.strip().lower())
        target_row = active_targets.get(target_key)
        for thin_index in range(1, 5):
            percent_columns[2 + ((thin_index - 1) * 2)].caption("")
            removal_column = percent_columns[3 + ((thin_index - 1) * 2)]
            thin_percent = removal_column.number_input(
                f"{thinning_species} {thinning_cohort} removal % {thin_index}",
                min_value=0.0,
                max_value=100.0,
                value=None,
                key=f"thinning_percent_{species_index}_{thin_index}",
                label_visibility="collapsed",
            )
            thin_year = thinning_years[thin_index - 1]
            if thin_percent is not None and thin_year is None:
                thinning_errors.append(f"Enter year for thinning {thin_index}.")
            elif thin_percent is not None and not thinning_species.strip():
                thinning_errors.append(f"Enter species for thinning row {species_index}.")
            elif thin_percent is not None and target_row is None:
                thinning_errors.append(f"Thinning row {species_index}: species/cohort must match an active species row.")
            elif thin_year is not None and thin_percent is not None:
                schedule_entry = {
                    "species": thinning_species,
                    "year": thin_year,
                    "removal_fraction": thin_percent / 100,
                }
                if thinning_cohort.strip():
                    schedule_entry["cohort_label"] = thinning_cohort.strip()
                thinning_schedule.append(schedule_entry)

    horizon = st.number_input("Horizon", min_value=1, max_value=100, value=None, key="simulation_horizon")
    if horizon is not None:
        for index, thin_year in enumerate(thinning_years, start=1):
            if thin_year is not None and thin_year > horizon:
                thinning_errors.append(f"Thinning {index}: year must be within the {horizon}-year horizon.")
    if thinning_errors:
        st.error(" ".join(sorted(set(thinning_errors))))
    input_errors = []
    if stand_id is None:
        input_errors.append("Enter a stand ID.")
    if not species_entries:
        input_errors.append("Enter at least one species row.")
    if input_errors:
        st.error(" ".join(input_errors))

    field_input = {
        "altitude": altitude,
        "soil_moisture": soil_moisture,
        "site_fertility": site_fertility,
        "horizon_years": horizon,
    }
    if species_entries:
        field_input["species_entries"] = species_entries
    field_input = {key: value for key, value in field_input.items() if value is not None}
    if thinning_schedule:
        field_input["thinning_schedule"] = thinning_schedule

    payload = {"stand_id": stand_id, "simulator": "r3pg", "input_mode": "field", "field_input": field_input}
    st.caption("Optionally show how key stand variables develop over the simulation horizon.")
    show_plots = st.checkbox("Show growth plots after simulation", key="show_growth_plots")
    c9, c10, c11 = st.columns(3)
    has_errors = bool(thinning_errors or input_errors)
    if c9.button("Preview defaults", disabled=has_errors):
        post("/simulation-runs/default-preview", payload)
    if c10.button("Preview r3PG tables", disabled=has_errors):
        post("/simulation-runs/r3pg-tables", payload)
    if c11.button("Run r3PG", disabled=has_errors):
        result = post("/simulation-runs", payload)
        if result and result.get("outputs"):
            st.session_state["last_simulation_run_id"] = result.get("id")
            st.session_state["last_stand_id"] = result.get("stand_id", stand_id)
            rows = [
                {key: value for key, value in item["output"].items() if key != "notes"}
                for item in result["outputs"]
            ]
            thinning_ages = {
                (species_row["output_label"], species_row["age"] + schedule["year"])
                for schedule in thinning_schedule
                for species_row in species_rows
                if normalize_species_name(schedule["species"]) == species_row["canonical"]
                and schedule.get("cohort_label", "").strip().lower() == species_row["cohort_label"].lower()
                and species_row["age"] is not None
                and species_row.get("output_label")
            }
            table = pd.DataFrame(rows).rename(
                columns={
                    "year": "Year",
                    "species": "Species",
                    "age_years": "Age",
                    "stems_per_ha": "N/ha",
                    "basal_area_m2_ha": "BA m²/ha",
                    "mean_dbh_cm": "DBH cm",
                    "mean_height_m": "H m",
                    "standing_volume_m3_ha": "Vol m³/ha",
                    "aboveground_biomass_t_ha": "AGB t/ha",
                    "mean_annual_increment_m3_ha_yr": "MAI m³/ha/y",
                    "canopy_cover": "Canopy cover",
                    "canopy_cover_max": "Canopy cover max",
                    "canopy_volume_fraction": "Canopy occupancy",
                    "canopy_volume_fraction_max": "Canopy occupancy max",
                }
            )
            table = table.drop(columns=["Canopy cover", "Canopy cover max"], errors="ignore")
            st.session_state["simulation_table"] = table
            st.session_state["thinning_ages"] = thinning_ages
            st.session_state["simulation_diagnostics"] = (result.get("summary") or {}).get("diagnostics") or []
            st.session_state["show_plots"] = show_plots
            styled_table = table.style.apply(
                lambda row: [
                    "background-color: #d9ead3" if (row["Species"], row["Age"]) in thinning_ages else ""
                ] * len(row),
                axis=1,
            ).format(precision=2)
            st.caption("Green rows indicate scheduled thinning years.")
            st.dataframe(styled_table, use_container_width=True)
            diagnostics = (result.get("summary") or {}).get("diagnostics") or []
            if diagnostics:
                with st.expander("Diagnostics"):
                    resolved_thinning = (result.get("summary") or {}).get("resolved_thinning") or []
                    if resolved_thinning:
                        st.caption("Resolved thinning targets are based on simulated stem number at thinning age.")
                        st.dataframe(
                            pd.DataFrame(resolved_thinning).rename(
                                columns={
                                    "species": "Species",
                                    "age": "Age",
                                    "removal_fraction": "Removal fraction",
                                    "stems_before": "N before",
                                    "stems_after": "N after",
                                }
                            ).style.format(precision=3),
                            use_container_width=True,
                        )
                    diagnostic_table = pd.DataFrame(diagnostics).rename(
                        columns={
                            "year": "Year",
                            "species": "Species",
                            "stems_start": "N start",
                            "mort_stress_sum": "Mort stress sum",
                            "mort_thinn_sum": "Self-thin sum",
                            "gamma_n_mean": "gammaN mean",
                            "biom_tree": "Tree biom",
                            "biom_tree_max": "Max tree biom",
                            "basal_area": "BA m²/ha",
                            "lai_max": "LAI max",
                            "lai_mean": "LAI mean",
                            "canopy_cover_max": "Canopy cover max",
                            "canopy_volume_fraction": "Canopy occupancy",
                            "canopy_volume_fraction_max": "Canopy occupancy max",
                        }
                    )
                    diagnostic_table = diagnostic_table.drop(columns=["stems_end", "Canopy cover max"], errors="ignore")
                    st.dataframe(diagnostic_table.style.format(precision=3), use_container_width=True)
                    st.session_state["diagnostic_table"] = diagnostic_table

with st.expander("Chat"):
    chat_session_id = st.session_state.get("chat_session_id")
    c_session, c_new = st.columns([3, 1])
    c_session.caption(f"Session: {chat_session_id or 'new'}")
    if c_new.button("New chat"):
        st.session_state.pop("chat_session_id", None)
        chat_session_id = None

    chat_stand_id = st.number_input(
        "Chat stand ID",
        min_value=1,
        value=st.session_state.get("last_stand_id", 3),
    )
    run_id = st.number_input(
        "Simulation run ID",
        min_value=1,
        value=st.session_state.get("last_simulation_run_id", 1),
    )
    question = st.text_area(
        "Question",
        key="chat_question",
        placeholder="Ask a question or follow-up about this stand and simulation.",
    )
    if st.button("Ask", disabled=not question.strip()):
        chat_payload = {
            "stand_id": chat_stand_id,
            "simulation_run_id": run_id,
            "question": question.strip(),
            "top_k": 3,
        }
        if chat_session_id:
            chat_payload["session_id"] = chat_session_id
        result = post(
            "/chat",
            chat_payload,
            show_json=False,
        )
        if result:
            st.session_state["chat_session_id"] = result.get("session_id")
            st.markdown(result.get("answer") or "No answer returned.")
            sources = result.get("retrieved_context") or []
            if sources:
                with st.expander("Retrieved context"):
                    for source in sources:
                        st.markdown(f"**{source.get('title', 'Source')}** · score {source.get('score')}")
                        st.caption(source.get("chunk_text", ""))

if st.session_state.get("simulation_table") is not None and st.session_state.get("show_plots"):
    st.divider()
    st.subheader("Simulation Plots")
    table = st.session_state["simulation_table"]
    thinning_ages = st.session_state.get("thinning_ages", set())
    plot_species = list(table["Species"].dropna().unique())
    active_colors = chart_colors(plot_species)
    plot_specs = [
        ("N/ha", "Stem number", "trees/ha"),
        ("BA m²/ha", "Basal area", "m²/ha"),
        ("DBH cm", "Mean diameter", "cm"),
        ("H m", "Mean height", "m"),
        ("Vol m³/ha", "Standing volume", "m³/ha"),
    ]
    plot_columns = st.columns(2)
    for index, (field, title, unit) in enumerate(plot_specs):
        plot_columns[index % 2].altair_chart(
            growth_chart(table, field, title, unit, active_colors),
            use_container_width=True,
        )
    total_volume_table = total_by_year(table, "Vol m³/ha", "Total Vol m³/ha")
    if not total_volume_table.empty:
        plot_columns[len(plot_specs) % 2].altair_chart(
            total_growth_chart(
                total_volume_table,
                "Total Vol m³/ha",
                "Total standing volume",
                "m³/ha",
            ),
            use_container_width=True,
        )
    diagnostic_table = st.session_state.get("diagnostic_table")
    if diagnostic_table is not None:
        with st.expander("Diagnostic Plots"):
            diagnostic_specs = [
                ("N start", "Stem number start", "trees/ha"),
                ("Mort stress sum", "Stress mortality sum", "t/ha/y"),
                ("LAI mean", "Mean leaf area index", "m²/m²"),
                ("LAI max", "Maximum leaf area index", "m²/m²"),
                ("Self-thin sum", "Density/self-thinning mortality sum", "trees/ha/y"),
                ("gammaN mean", "Mean mortality factor gammaN", "factor"),
                ("Tree biom", "Tree biomass", "t/tree"),
                ("Max tree biom", "Maximum tree biomass", "t/tree"),
                ("Canopy occupancy", "Canopy occupancy", "proportion"),
                ("Canopy occupancy max", "Maximum canopy occupancy", "proportion"),
            ]
            diagnostic_columns = st.columns(2)
            for index, (field, title, unit) in enumerate(diagnostic_specs):
                diagnostic_columns[index % 2].altair_chart(
                    growth_chart(diagnostic_table, field, title, unit, active_colors),
                    use_container_width=True,
                )
