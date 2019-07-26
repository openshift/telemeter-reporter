# -*- coding: utf-8 -*-
from string import Template
from typing import Dict, List

import certifi
import prometheus_api_client
import requests
from tabulate import tabulate

from .uhc import UnifiedHybridClient


class SLAReporter:
    """
    Generate formatted reports on SLA compliance
    """

    caution_threshold = 0.01
    default_css = """<style>
            .danger {color: red; font-weight: bold;}
            .caution {color: darkorange; font-weight: bold;}
            .success {color: green;}
        </style>"""

    def __init__(self, config: dict):
        """
        Instantiate a SLAReporter object

        :param config: (dict) the "settings" for this class, including URLs
            and rules. Usually originates from a YAML file.
        """
        self.config = config

        # Connect to Telemeter-LTS
        if not self.__check_ssl_certs(self.config["api"]["telemeter"]["url"]):
            raise Exception("Can't connect to Telemeter-LTS")
        self.pc = prometheus_api_client.prometheus_connect.PrometheusConnect(
            url=self.config["api"]["telemeter"]["url"],
            headers={
                "Authorization": "bearer " + self.config["api"]["telemeter"]["token"]
            },
            disable_ssl=False,
        )

        # Connect to UHC
        self.uhc = UnifiedHybridClient(
            config["api"]["uhc"]["url"], config["api"]["uhc"]["token"]
        )

    def get_cluster_ids(self, search_query: str) -> Dict[str, str]:
        """
        Gets the names and external_ids of all clusters matching
        a search query from the UHC CLI

        :param search_query: (str) a UHC search string (see UHC API docs)
        :returns: (dict) a dict with selected cluster names as keys and
            their external_ids as values
        """
        cluster_list = self.uhc.search_clusters(search_query)
        return {
            x["name"]: "_id='{}'".format(x["external_id"])
            for x in cluster_list["items"]
            if "external_id" in x.keys()
        }

    def generate_report(self, cluster_ids: Dict[str, str], fmt: str) -> List[List[str]]:
        """
        Generate a raw SLA report by running each configured query
        against the provided list of cluster IDs

        :param cluster_ids: (dict) a dict with selected cluster names as
            keys and their external_ids as values
        :param fmt: (str) specifies what kind of formatting padding should
            be included. For example, specifying "html" will wrap numbers
            in <span> tags, "plain" wraps with BASH color specifiers, etc.
            Providing None disables all wrapping.
        :returns: (list) a report in form of a table (i.e. list of lists)
        """
        table = []
        for name, selector in cluster_ids.items():
            row = [name]
            for rule in self.config["rules"]:
                query_params = {
                    **{k: v for k, v in rule.items() if k != "query"},
                    **{"sel": selector},
                }
                query = Template(rule["query"]).substitute(**query_params)
                sla = float(rule["sla"]) * 100
                try:
                    query_res = self.pc.custom_query(query)
                    sli = round(float(query_res[0]["value"][1]) * 100, 4)
                    row += [
                        str(sla) + ("&#37;" if fmt == "html" else "%"),
                        self.__format_sli(sli, sla, fmt),
                    ]
                except:
                    #print("Query failed:" + str(query)) # TODO RE-ENABLE LOGGING
                    row += [str(sla) + ("&#37;" if fmt == "html" else "%"), ""]
            table.append(row)

        return table

    def generate_headers(self) -> List[str]:
        """
        Generate the header row of the report based on the configured rules

        :returns: a single list representing the header row
        """
        return ["Cluster"] + list(
            sum(
                [
                    (r["name"] + " SLA", r["name"] + " Perf.")
                    for r in self.config["rules"]
                ],
                (),
            )
        )

    @classmethod
    def format_report(cls, headers: List[str], table: List[List[str]], fmt: str, css: str = None, ) -> str:
        """
        Format a pre-generated report using tabulate and print to string

        Basically, this wraps around tabulate, but does the work of adding
        CSS styles for you. Optionally, you can provide your own CSS style

        :param headers: (list) the header row of the report
        :param table: (list) the contents of the report
        :param fmt: (str) passed to tabulate as the "tablefmt" param
        :param css: (str) optional custom CSS <style> block
        """
        css = (css or cls.default_css) if fmt == "html" else ""
        return css + tabulate(table, headers, tablefmt=fmt, stralign="center")

    @staticmethod
    def __check_ssl_certs(url: str) -> bool:
        """
        Checks if the Red Hat SSL CA certs are installed by connecting
        to a URL that uses them.

        :param url: (str) an HTTPS URL utilizing Red Hat-signed certificates
        :returns: (bool) true if we could successfully connect to the URL
        """
        retries = 3
        success = False
        while not success and retries > 0:
            retries -= 1
            try:
                requests.get(url)
                success = True
            except requests.exceptions.SSLError:
                cafile = certifi.where()
                with open("RHCertBundle.pem", "rb") as infile:
                    customca = infile.read()
                with open(cafile, "ab") as outfile:
                    outfile.write(customca)

        return success

    @classmethod
    def __format_sli(cls, sli: float, sla: float, fmt: str = "html") -> str:
        """
        Adds CSS formatting to the value of an SLI based on whether
        or not it complies with SLA

        :param sli: (float) the current value of the SLI
        :param sla: (float) the minimum "good" value of the SLI
        :param fmt: (str) What kind of formatting to apply. Options
            include "html", "plain", "simple", "grid", "fancy_grid"
        :returns: (str) a formatted HTML string
        """
        if sli - sla < 0:
            html_template = "<span class='danger'>{}&#37;</span>"
            shell_template = "\033[1;31m{}%\033[0m"
        elif sli - sla < cls.caution_threshold:
            html_template = "<span class='caution'>{}&#37;</span>"
            shell_template = "\033[1;33m{}%\033[0m"
        else:
            html_template = "<span class='success'>{}&#37;</span>"
            shell_template = "\033[0;32m{}%\033[0m"

        if fmt in ["plain", "simple", "grid", "fancy_grid"]:
            return shell_template.format(sli)
        elif fmt == "html":
            return html_template.format(sli)
        else:
            return str(sli)
