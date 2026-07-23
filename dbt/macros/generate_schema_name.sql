{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {#- schema_suffix (default empty): var-driven isolation suffix for PV §9.3 sensitivity builds. Empty =>
        IDENTICAL to prod (no-op). Set (e.g. 'sens') => every dataset gains the suffix, so a --select'd +
        --defer'd variant build writes ONLY to nhl_<schema>_<suffix> and never touches prod. -#}
    {%- set suffix = var('schema_suffix', '') -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}{% if suffix %}_{{ suffix }}{% endif %}
    {%- else -%}
        {#- Use custom schema as standalone dataset, not appended -#}
        nhl_{{ custom_schema_name }}{% if suffix %}_{{ suffix }}{% endif %}
    {%- endif -%}
{%- endmacro %}
