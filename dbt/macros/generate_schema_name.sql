{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {#- Use custom schema as standalone dataset, not appended -#}
        nhl_{{ custom_schema_name }}
    {%- endif -%}
{%- endmacro %}
