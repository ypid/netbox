# Demo Data

Sample data is included with NetBox for demonstration and development purposes. The data is stored as a collection of Django fixtures in JSON format.

## Loading Demo Data

```
./manage.py loaddata ../demo_data.json
```

## Saving Demo Data

!!! warning
    Do not overwrite the stock demo data unless you are intentionally updating it for a new release.

```
./manage.py dumpdata --natural-foreign --natural-primary --indent 4 --format json -o <filename>
```
