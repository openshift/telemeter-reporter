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
Configuration is provided via a YAML file (and in certain cases, environmental variables). The command line 
tool checks three locations (in order) for a config file:
 1. `TELEMETER_REPORTER_CONFIG` environment variable
 2. argument to the `--config` or `-c` flag
 3. `~/.telemeter_reporter.yml`

A sample config file is provided (`reporter_confg.yml.tmpl`). An explanation of each key is below. All keys are required
unless otherwise noted.
- `css`: provide a Cascading Style Sheet here to be injected into HTML-formatted reports (optional)
- `html`: provide HTML here to override the built-in template. Any instances of `${title}`, `${style}`, `${table}`, or 
`${footer}` will be replaced by (respectively) the report title, raw CSS (either the built-in stylesheet or the value of
`css` from above), the HTML table displaying the results, or a footer showing when the report was generated and how long
it took (optional)
- `api.telemeter.url`: URL to any service providing a Prometheus-compatible API
- `api.telemeter.token`: Log-in token for the Telemeter API (i.e. OAuth) **(can be left out if `TELEMETER_TOKEN` env-var is set)**
- `api.uhc.url`: URL for the UHC HTTP API
- `api.uhc.public_key`: Public key for verifying the authenticity of the provided JWT (can be left out to disable token 
verification, but this is not recommended. Red Hat's public key is provided in the sample config file)
- `api.uhc.token`: "Offline access" JWT token for UHC API **(can be left out if `UHC_TOKEN` env-var is set)**
- `clusters`: provide a list of UHC queries as strings here. Each the cluster IDs returned by each query will be 
reported on **(can be overridden with the `--uhc-query` flag)**
- `global_vars`: provide a list of strings/ints/floats here to make them available as global variables to each rule. For
example, providing `- foo: "bar"` here will replace any instance of `${foo}` in each rule query with `bar`. At a minimum,
you should provide a `duration` variable (in days) here **(can be overridden with the `--override` flag)**
- `rules`: provide a list of SLI rules to evaluate (see below)
  - `rules.name`: a human-readable name for the rule
  - `rules.description`: a human-readable description for the rule (optional, only shown in HTML tooltips)
  - `rules.goal`: the target-value for the query result. Usually a percentage represented as a float between 0 and 1.0
  - `rules.query`: a valid PromQL query that returns the current value of the SLI (which will be compared to the goal).
Any instance of `${sel}` will be replaced with `_id=<cluster_id>`. You may also use global variables (see `global_vars`
above)

 
### Command line tool
```
$ telemeter-reporter -h
usage: telemeter-reporter [-h] [-c PATH] [-f FMT] [-u QUERY] [-t TITLE] [-b]
                          [-a] [-m] [-p] [-l LEVEL] [-o VARS]
                          output

Tool for generating reports on SLA/SLO compliance using Telemeter-LTS data

positional arguments:
  output                Destination path for the generated report (- = stdout)

optional arguments:
  -h, --help            show this help message and exit
  -c PATH, --config PATH
                        Path to YAML file containing configuration data.
                        Default: ~/.telemeter_reporter.yml
  -f FMT, --format FMT  Format for the report. Can be provided multiple times
                        (see --auto-ext). Options: ['simple', 'plain', 'html',
                        'csv', 'grid', 'fancy_grid', 'github', 'jira',
                        'latex']. Default: simple
  -u QUERY, --uhc-query QUERY
                        Report on all clusters returned by this query to the
                        UHC API
  -t TITLE, --title TITLE
                        Optional title for HTML reports
  -b, --no-browser      Don't open the resulting report in a web browser (if
                        HTML report is selected)
  -a, --auto-ext        Automatically append a file extension onto the
                        provided output path. Enabled by default when --format
                        is used multiple times. Has no effect when output =
                        stdout.
  -m, --minify          Minify HTML output
  -p, --parents         Same behavior as mkdir's --parents option. Creates
                        parent directories in the output path if necessary.
  -l LEVEL, --log LEVEL
                        Set the verbosity/logging level. Options: ['critical',
                        'error', 'warning', 'info', 'debug']
  -o VARS, --override VARS
                        Override global variables set in the configuration
                        file. Provide a valid Python dict string, e.g.
                        "{'duration': 28}"
```
Note: the `-u` parameter overrides any `clusters` list provided in a config file.

### Examples
#### Simple 28-day report
```
$ telemeter-reporter -f simple -o "{'duration':28}"
   Cluster       CtrlPlane    CtrlPlane    CtrlPlane    CtrlPlane    CtrlPlane    CtrlPlane
                  General      General        API          API         etcd         etcd
                   Goal         Perf.        Goal         Perf.        Goal         Perf.
--------------  -----------  -----------  -----------  -----------  -----------  -----------
test-cluster-1    99.500%      100.00%      99.900%      99.999%      99.900%      95.982% 
test-cluster-2    99.500%      100.00%      99.900%      99.999%      99.900%      95.992% 
```
#### Output to GitHub-Flavored Markdown file
```
$ telemeter-reporter -f github output.md
```
`output.md` Contents:

| Cluster | CtrlPlane General Goal | CtrlPlane General Perf. | CtrlPlane API Goal | CtrlPlane API Perf. | CtrlPlane etcd Goal | CtrlPlane etcd Perf. | CtrlPlane Latency Goal | CtrlPlane Latency Perf. | Registry General Goal | Registry General Perf. | Compute General Goal | Compute General Perf. | Compute Resiliency Goal | Compute Resiliency Perf. | Support Monitoring Goal | Support Monitoring Perf. |
|----------------|--------------------------|---------------------------|----------------------|-----------------------|-----------------------|------------------------|--------------------------|---------------------------|-------------------------|--------------------------|------------------------|-------------------------|---------------------------|----------------------------|---------------------------|----------------------------|
| osd-v4stg-aws  |         99.500%          |          100.00%          |       99.900%        |        99.999%        |        99.900%        |        95.982%         |         99.500%          |          100.00%          |         99.000%         |         95.982%          |        99.500%         |         100.00%         |          99.000%          |          100.00%           |          99.990%          |          100.00%           |
| osd-v4prod-aws |         99.500%          |          100.00%          |       99.900%        |        99.999%        |        99.900%        |        95.992%         |         99.500%          |          100.00%          |         99.000%         |         95.942%          |        99.500%         |         98.800%         |          99.000%          |          98.353%           |          99.990%          |          100.00%           |