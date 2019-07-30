# -*- coding: utf-8 -*-
import csv
import io
import logging
from string import Template
from typing import Dict, List, Union

import certifi
import prometheus_api_client
import requests
from tabulate import tabulate

from .uhc import UnifiedHybridClient


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
        self.uhc = UnifiedHybridClient(config["api"]["uhc"]["url"], config["api"]["uhc"]["token"])
        self.logger.info("Connected to UHC API")

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

    def get_cluster_ids(self, search_query: str) -> Dict[str, str]:
        """
        Gets the names and external_ids of all clusters matching
        a search query from the UHC CLI

        :param search_query: (str) a UHC search string (see UHC API docs)
        :returns: (dict) a dict with selected cluster names as keys and
            their external_ids as values
        """
        cluster_list = self.uhc.search_clusters(search_query)
        return {x["name"]: "_id='{}'".format(x["external_id"]) for x in cluster_list["items"] if
                "external_id" in x.keys()}

    def generate_report(self, cluster_ids: Dict[str, str]) -> Dict[
        str, Dict[str, Dict[str, float]]]:
        """
        Generate a raw SLA report by running each configured query
        against the provided list of cluster IDs

        :param cluster_ids: (dict) a dict with selected cluster names as
            keys and their external_ids as values.
        :returns: (dict) raw report data in a nested dictionary
        """
        raw_report = {}
        for cluster_name, selector in cluster_ids.items():
            raw_report[cluster_name] = {}
            for rule in self.config["rules"]:
                raw_report[cluster_name][rule['name']] = {}
                try:
                    query_params = {**{k: v for k, v in rule.items() if k != "query"},
                                    **self.config['global_vars'], **{"sel": selector}, }
                except KeyError:
                    query_params = {**{k: v for k, v in rule.items() if k != "query"},
                                    **{"sel": selector}, }
                query = Template(rule["query"]).substitute(**query_params)
                raw_report[cluster_name][rule['name']]['goal'] = float(rule['goal']) * 100
                self.logger.info(
                    "Resolving '{}' for cluster '{}'...".format(rule['name'], cluster_name))
                # noinspection PyBroadException
                try:
                    self.logger.debug("REQUEST: " + query)
                    query_res = self.pc.custom_query(query)
                    self.logger.debug("RESPONSE: " + str(query_res))
                    raw_report[cluster_name][rule['name']]['sli'] = float(
                        query_res[0]["value"][1]) * 100
                except Exception as ex:
                    raw_report[cluster_name][rule['name']]['sli'] = None
                    self.logger.warning(
                        "Failed to resolve '{}' for cluster '{}': {}".format(rule['name'],
                                                                             cluster_name, str(ex)))
                    self.logger.info("Full exception: " + repr(ex))
        return raw_report

    def generate_headers(self) -> List[str]:
        """
        Generate the header row of the report based on the configured rules

        :returns: a single list representing the header row
        """
        return ["Cluster"] + list(
            sum([(r["name"] + " Goal", r["name"] + " Perf.") for r in self.config["rules"]], (), ))

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
                try:
                    with open("RHCertBundle.pem", "rb") as infile:
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
