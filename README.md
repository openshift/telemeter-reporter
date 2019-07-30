# telemeter-reporter
Python tool for generating SLA compliance reports based on [Telemeter](https://github.com/openshift/telemeter/) data.

For the original prototype script, see the `notebook` directory.

## Installation
Install with `pip` (Python 3 only)
```
pip3 install telemeter-reporter
```

## Usage
### Configuration
Configuration is typically provided with via a YAML file. By default, the command line tool looks for a 
`.telemeter-reporter.yml` under `$HOME`. Alternatively, you can specify the path to the config file with the `-c` flag.

A sample config file is provided (`reporter_confg.yml.tmpl`). An explanation of each key is below:
- `css`: provide a Cascading Style Sheet here to be injected into HTML-formatted reports.
- `api:telemeter:url`: URL to any service providing a Prometheus-compatible API
- `api:telemeter:token`: Log-in token for the Telemeter API (i.e. OAuth)
- `api:uhc:url`: URL for the UHC HTTP API
- `api:uhc:public_key`: Public key for verifying the authenticity of the provided JWT
- `api:uhc:token`: "Offline access" token for UHC API
- `clusters`: provide a list of UHC queries as strings here. Each the cluster IDs returned by each query will be reported on
- `global_vars`: provide a list of strings/ints/floats here to make them available as global variables to each rule. For
example, providing `- foo: "bar"` here will replace any instance of `${foo}` in each rule query with `bar`. At a minimum,
you should provide a `duration` variable (in days) here.
- `rules`: provide a list of SLI rules to evaluate (see below)
  - `rules:name`: a human-readable name for the rule
  - `rules:goal`: the target-value for the query result. Usually a percentage represented as a float between 0 and 1.0
  - `rules:query`: a valid PromQL query that returns the current value of the SLI (which will be compared to the goal)
 
### Command line tool
```
$ telemeter-reporter -h
usage: telemeter-reporter [-h] [-c PATH] [-f FMT] [-u QUERY] [-t TITLE] [-b]
                          [-l LEVEL] [-o VARS]
                          output

Tool for generating reports on SLA/SLO compliance using Telemeter-LTS data

positional arguments:
  output                Path to where to save the generated report (- =
                        stdout)

optional arguments:
  -h, --help            show this help message and exit
  -c PATH, --config PATH
                        Path to YAML file containing configuration data
                        (default: ~/.telemeter_reporter.yml)
  -f FMT, --format FMT  Format for the report. Options: ['simple', 'plain',
                        'html', 'csv', 'grid', 'fancy_grid', 'github', 'jira',
                        'latex'] (default: simple)
  -u QUERY, --uhc-query QUERY
                        Report on all clusters returned by this query to the
                        UHC API (default: None)
  -t TITLE, --title TITLE
                        Optional title for HTML reports (default: None)
  -b, --no-browser      Don't open the resulting report in a web browser (if
                        HTML report is selected) (default: False)
  -l LEVEL, --log LEVEL
                        Set the verbosity/logging level. Options: ['critical',
                        'error', 'warning', 'info', 'debug'] (default:
                        warning)
  -o VARS, --override VARS
                        Override global variables set in the configuration
                        file. Provide a valid Python dict string, e.g.
                        "{'duration': 28}" (default: None)

```
Note: the `-u` parameter overrides any `clusters` list provided in a config file.
