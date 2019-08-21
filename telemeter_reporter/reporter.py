# -*- coding: utf-8 -*-
import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from string import Template
from typing import Dict, List, Union

import certifi
import prometheus_api_client
import requests
from tabulate import tabulate

from .uhc import Cluster, UnifiedHybridClient


class SLIReporter(object):
    """
    Generate formatted reports on SLI performance
    """
    logger = logging.getLogger("SLIReporter")

    caution_threshold = 0.01
    default_css = """<style>
            .danger {color: red; font-weight: bold;}
            .caution {color: darkorange; font-weight: bold;}
            .success {color: green;}
        </style>"""

    default_html = """<!DOCTYPE html> 
        <html>
            <head>
                <meta charset="utf-8">
                <title>${title}</title>
                <link rel="stylesheet" href="https://unpkg.com/balloon-css/balloon.min.css">
                <style>
                    ${style}
                </style>
            </head>
            <body>
                <h2>${title}</h2>
                ${table}
                <p>${footer}</p>
            </body>
        </html>"""

    def __init__(self, config: dict):
        """
        Instantiate a SLIReporter object

        :param config: (dict) the "settings" for this class, including URLs
            and rules. Usually originates from a YAML file.
        """
        self.config = config

        # Connect to Telemeter-LTS
        if not self.__check_ssl_certs(self.config["api"]["telemeter"]["url"]):
            self.logger.error(
                "Couldn't securely connect to {}.".format(self.config["api"]["telemeter"]["url"]))
            raise Exception("Can't connect to Telemeter-LTS")
        self.pc = prometheus_api_client.prometheus_connect.PrometheusConnect(
            url=self.config["api"]["telemeter"]["url"],
            headers={"Authorization": "bearer " + self.config["api"]["telemeter"]["token"]},
            disable_ssl=False, )
        self.logger.info("Connected to Telemeter-LTS")

        # Connect to UHC
        try:
            self.uhc = UnifiedHybridClient(config["api"]["uhc"]["url"],
                                           config["api"]["uhc"]["token"],
                                           config["api"]["uhc"]["public_key"])
            self.logger.info("Connected to UHC API")
        except KeyError:
            self.uhc = UnifiedHybridClient(config["api"]["uhc"]["url"],
                                           config["api"]["uhc"]["token"])
            self.logger.info("Connected to UHC API (unverified)")

        # Setup CSS
        try:
            self.css = self.config['css']
        except KeyError:
            self.css = self.default_css

        # Setup HTML
        try:
            self.html = self.config['html']
        except KeyError:
            self.html = self.default_html

    def get_clusters(self, search_query: str, query_time: datetime = None) -> List[Cluster]:
        """
        Gets the all clusters matching a search query from the UHC CLI that have
        external_ids

        :param search_query: (str) a UHC search string (see UHC API docs)
        :param query_time: (datetime) if provided, only returns clusters that were created before
            this point in time
        :returns: (list) a list of uhc.Cluster objects matching the query
        """
        cluster_list = self.uhc.search_clusters(search_query)
        if query_time:
            return list(
                x for x in cluster_list if x.external_id and x.creation_timestamp < query_time)
        else:
            return list(x for x in cluster_list if x.external_id)

    @staticmethod
    def __adjust_duration(duration: int, query_time: datetime, creation_timestamp: datetime) -> int:
        """
        Corrects query durations based on cluster age. If the age of the cluster
        (relative to the "effective now" of the query) is shorter than the
        requested duration, return a new duration that's slightly less than the
        cluster age

        :param duration: (int) user-requested duration to be corrected
        :param query_time: (datetime or None) the time at which the user
            requested the query be run, if the user set one. If None, assume
            datetime.now(timezone.utc). Must be timezone-aware datetime
        :param creation_timestamp: (datetime) the creation timestamp of the cluster
        :returns: (int or None) the adjusted duration, or None if no adjustment
            is necessary.
        """
        effective_now = query_time or datetime.now(timezone.utc)
        duration_start = effective_now - timedelta(days=duration)
        if duration_start < creation_timestamp:
            # New duration = floor(# of days between effective_now and cluster creation)
            return (effective_now - creation_timestamp).days

    def generate_report(self, clusters: List[Cluster], query_time: datetime = None,
                        adjust_duration: bool = True) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Generate a raw SLA report by running each configured query
        against the provided list of cluster IDs

        :param clusters: (list) a list of Clusters to report on
        :param query_time: (datetime) if provided, tells Telemeter to query as if
            it was sometime in the past. Must be a timezone-aware datetime
        :param adjust_duration: (bool) if True, adjust the duration parameter on
            queries for clusters that were created before the start time of the
            duration. E.g., if a cluster was created 3 days ago, but a 28-day
            report is requested, adjust the duration to 3 days
        :returns: (dict) raw report data in a nested dictionary
        """
        raw_report = {}
        for cluster in clusters:
            selector = "_id='{}'".format(cluster.external_id)

            # Modify duration if the cluster was created before the start time of the requested
            # global duration.
            new_cluster_duration = None
            if adjust_duration and 'duration' in self.config['global_vars']:
                new_cluster_duration = self.__adjust_duration(
                    int(self.config['global_vars']['duration']), query_time,
                    cluster.creation_timestamp)
                if new_cluster_duration:
                    self.logger.warning("'{0}' was created only {1} days before {2}, so capping "
                                        "global query duration for this cluster at {1}d".format(
                        cluster.name, new_cluster_duration, query_time or "today"))
                    # Update cluster name
                    cluster = cluster._replace(name=cluster.name + '*')

            raw_report[cluster.name] = {}
            for rule in self.config["rules"]:
                raw_report[cluster.name][rule['name']] = {}

                # Prepare PromQL query parameters
                try:
                    query_params = {**self.config['global_vars'],
                                    **{k: v for k, v in rule.items() if k != "query"},
                                    **{"sel": selector}, }
                except KeyError:
                    query_params = {**{k: v for k, v in rule.items() if k != "query"},
                                    **{"sel": selector}, }

                # If cluster-level duration override is set, implement it
                if new_cluster_duration:
                    query_params['duration'] = new_cluster_duration

                # Modify duration like above. This handles the case where a rule has its own local
                # duration variable defined that overrides the global one
                if adjust_duration and 'duration' in query_params:
                    new_rule_duration = self.__adjust_duration(int(query_params['duration']),
                                                               query_time,
                                                               cluster.creation_timestamp)
                    if new_rule_duration:
                        query_params['duration'] = new_rule_duration
                        self.logger.warning(
                            "'{0}' was created only {1} days before {2}, so capping "
                            "'{3}' query duration at {1}d".format(cluster.name, new_rule_duration,
                                                                  query_time.now if query_time else "today",
                                                                  rule['name']))

                # Do the substitution
                query = Template(rule["query"]).substitute(**query_params)
                raw_report[cluster.name][rule['name']]['goal'] = float(rule['goal']) * 100
                self.logger.info(
                    "Resolving '{}' for cluster '{}' at time {}...".format(rule['name'],
                                                                           cluster.name,
                                                                           query_time or "now"))
                # noinspection PyBroadException
                try:
                    self.logger.debug("REQUEST: " + query)
                    if query_time:
                        query_res = self.pc.custom_query(query, params={
                            'time': str(int(query_time.timestamp()))})
                    else:
                        query_res = self.pc.custom_query(query)
                    self.logger.debug("RESPONSE: " + str(query_res))
                    raw_report[cluster.name][rule['name']]['sli'] = float(
                        query_res[0]["value"][1]) * 100
                except Exception as ex:
                    raw_report[cluster.name][rule['name']]['sli'] = None
                    self.logger.warning(
                        "Failed to resolve '{}' for cluster '{}': {}".format(rule['name'],
                                                                             cluster.name, str(ex)))
                    self.logger.info("Full exception: " + repr(ex))
        return raw_report

    def generate_headers(self, html_tooltips: bool = False) -> List[str]:
        """
        Generate the header row of the report based on the configured rules

        :param html_tooltips: (bool) if True, add HTML span tags to the output which enable CSS
            description tooltips
        :returns: a single list representing the header row
        """
        if html_tooltips:
            prefix = "<span data-balloon-length='large' data-balloon-pos='up' " \
                     "aria-label='{desc}'>{name} {t}</span>"

            head_gen = [(prefix.format(name=r['name'],
                                       desc=(r['description'] if 'description' in r else "n/a"),
                                       t="Goal"), prefix.format(name=r['name'], desc=(
                r['description'] if 'description' in r else "n/a"), t="Perf.")) for r in
                        self.config["rules"]]

        else:
            head_gen = [(r["name"] + " Goal", r["name"] + " Perf.") for r in self.config["rules"]]

        return ["Cluster"] + list(sum(head_gen, (), ))

    def format_report(self, headers: List[str], raw_report: Dict[str, Dict[str, Dict[str, float]]],
                      fmt: str, color: bool, title: str = None, footer: str = None) -> str:
        """
        Format a pre-generated report using tabulate and print to string

        Basically, this function adds to the capabilities of tabulate by
        adding colors and HTML styling (if fmt='html')

        :param headers: (list) the header row of the report
        :param raw_report: (dict) the contents of the report
        :param fmt: (str) passed to tabulate as the "tablefmt" param
        :param color: (bool) whether or not to include color styles
        :param title: (str) optional title to display on the report
        :param footer: (str) optional footer to display on the report
        """
        table = []
        for cluster_name, rules in raw_report.items():
            row = [cluster_name]
            for rule_name, scores in rules.items():
                sli_f = self.__format_sli(value=scores['sli'], goal=scores['goal'],
                                          fmt=(fmt if fmt != 'csv' else None), color=color)
                goal_f = self.__format_sli(value=scores['goal'], goal=None,
                                           fmt=(fmt if fmt != 'csv' else None), color=False)
                row += [goal_f, sli_f]
            table.append(row)
        if fmt == 'csv':
            str_buff = io.StringIO()
            csv_writer = csv.writer(str_buff)
            for row in [headers] + table:
                csv_writer.writerow(row)
            formatted_report = str_buff.getvalue()
            str_buff.close()
            return formatted_report
        elif fmt == 'html':
            table_html = tabulate(table, headers, tablefmt=fmt, stralign="center")
            return Template(self.html).safe_substitute(style=self.css, table=table_html,
                                                       title=title, footer=footer)
        else:
            return tabulate(table, headers, tablefmt=fmt, stralign="center")

    @classmethod
    def __check_ssl_certs(cls, url: str) -> bool:
        """
        Checks if the Red Hat SSL CA certs are installed by connecting
        to a URL that uses them.

        :param url: (str) an HTTPS URL utilizing Red Hat-signed certificates
        :returns: (bool) true if we could successfully connect to the URL
        """
        cls.logger.debug("Attempting secure connection to " + url)
        retries = 2
        success = False
        while not success and retries > 0:
            retries -= 1
            try:
                response = requests.get(url)
                cls.logger.debug("Received status code " + str(response.status_code))
                success = True
            except requests.exceptions.SSLError:
                cls.logger.warning("SSL certificate error. {} retries left".format(retries))
                ca_file = certifi.where()
                # Load config file
                if os.getenv('TELEMETER_SSL_CA'):
                    new_ca_path = os.path.expanduser(os.getenv('TELEMETER_SSL_CA'))
                    cls.logger.info(
                        "Loading SSL CA from {} (set via TELEMETER_SSL_CA env-var)".format(
                            new_ca_path))
                else:
                    new_ca_path = "RHCertBundle.pem"

                try:
                    with open(new_ca_path, "rb") as infile:
                        custom_ca = infile.read()
                    with open(ca_file, "ab") as outfile:
                        outfile.write(custom_ca)
                        cls.logger.info("Added Red Hat CA to certificate store")
                except FileNotFoundError:
                    cls.logger.warning("No RHCertBundle.pem found. Please add the Red Hat CA "
                                       "certificate to your system's certificate store, or place "
                                       "a certificate bundle file named 'RHCertBundle.pem' in the "
                                       "working directory and try again.")

        return success

    @classmethod
    def __format_sli(cls, value: Union[float, None], goal: Union[float, None], fmt: str,
                     color: bool) -> str:
        """
        Adds CSS formatting to the value of an SLI based on whether
        or not it complies with SLA

        :param value: (float) the current value of the SLI
        :param goal: (float) the minimum "good" value of the SLI
        :param fmt: (str) What kind of formatting to apply. Options
            include "html", "plain", "simple", "grid", "fancy_grid"
        :param color: (bool) whether or not to apply coloring
        :returns: (str) a formatted HTML string
        """
        if value is None:
            value = 0
            html_template = "--"
            shell_template = "--"
        elif color:
            if value - goal < 0:
                html_template = "<span class='danger'>{}&#37;</span>"
                shell_template = "\033[1;31m{}%\033[0m"
            elif value - goal < cls.caution_threshold:
                html_template = "<span class='caution'>{}&#37;</span>"
                shell_template = "\033[1;33m{}%\033[0m"
            else:
                html_template = "<span class='success'>{}&#37;</span>"
                shell_template = "\033[0;32m{}%\033[0m"
        else:
            html_template = "{}&#37;"
            shell_template = "{}%"

        rounded_sli = '{:0.3f}'.format(value)[:6]
        if fmt == "html":
            return html_template.format(rounded_sli)
        elif fmt is not None:
            return shell_template.format(rounded_sli)
        else:
            return str(value)
