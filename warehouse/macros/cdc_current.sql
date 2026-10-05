{# Current rows of one source table: latest version per id (FINAL), not deleted, and newer than the last TRUNCATE. #}
{% macro cdc_current(tbl) %}
select payload, _ingested_at as _loaded_at
from {{ source('raw', 'cdc_events') }} final
where tbl = '{{ tbl }}'
  and op != 'd'
  and lsn > (select max(lsn) from {{ source('raw', 'cdc_truncates') }})
{% endmacro %}
