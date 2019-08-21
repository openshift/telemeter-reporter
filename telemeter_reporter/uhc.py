# -*- coding: utf-8 -*-
import datetime
import logging
from typing import List, NamedTuple

import jwt
import requests


class Cluster(NamedTuple):
    id: str
    name: str
    external_id: str
    creation_timestamp: datetime.datetime


class UnifiedHybridClient(object):
    """
    Limited access to the UHC API for authentication and cluster searching
    """
    logger = logging.getLogger("UnifiedHybridClient")

    def __init__(self, api_url: str, offline_token: str, public_key: str = None):
        """
        Instantiate a UnifiedHybrid client object

        :param api_url: (str) the URL for the UHC API
        :param offline_token: (str) a JSON Web Token string with the
            "offline_access" permission. Usually obtained from
            https://cloud.redhat.com/openshift/token
        :param public_key: (str) the RSA public key that corresponds
            to the JSON Web Token you provide. Hint: https://jwt.io/
            can extract this from a JWT for you
        """

        self.api_url = api_url
        self.offline_token = offline_token.strip()
        self.public_key = public_key.strip() if public_key is not None else public_key

        # Extract info from the offline token
        if self.public_key is None:
            self.logger.warning(
                "Unable to validate provided UHC offline_access token. Provide a value for "
                "api.uhc.public_key in the config file to enable validation")
        ot_decoded = jwt.decode(self.offline_token, self.public_key, algorithms="RS256",
                                verify=(self.public_key is not None), audience="cloud-services",
                                options={'verify_exp': False})
        self.iss_url = ot_decoded["iss"]
        self.client_id = ot_decoded["aud"]

    def __get_access_token(self) -> str:
        """
        Obtain a short-lived access token from the SSO service

        :returns: (str) a short-lived access token
        """
        response = requests.post("{}/protocol/openid-connect/token".format(self.iss_url),
                                 data={"grant_type":    "refresh_token",
                                       "client_id":     self.client_id,
                                       "refresh_token": self.offline_token, },
                                 headers={"accept": "application/json"}, )
        try:
            return response.json()["access_token"]
        except KeyError:
            self.logger.critical(
                "Unable to obtain OpenID access token from {}. Response: {}".format(self.iss_url,
                                                                                    str(response)))

    def search_clusters(self, query: str) -> List[Cluster]:
        """
        Query a list of clusters from the UHC HTTP API.

        :param query: (str) Specifies the search criteria. This syntax of
            this parameter is similar to the syntax of the WHERE clause of
            an SQL statement, but using the names of the attributes of the
            cluster instead of the names of the columns of a table.
        :returns: (list) a list of Cluster objects returned from the API
        """
        self.logger.info("Querying UHC API for clusters matching \"{}\"".format(query))
        response = requests.get("{}/api/clusters_mgmt/v1/clusters".format(self.api_url),
                                headers={"accept":        "application/json",
                                         "Authorization": "Bearer " + self.__get_access_token(), },
                                params={"search": query}, verify=True, )
        if response.status_code == 200:
            data = response.json()
            self.logger.info("UHC API returned {} clusters".format(len(data['items'])))
        else:
            raise Exception(
                "HTTP Status Code {} ({})".format(response.status_code, response.content))

        cluster_list = []
        for c in data['items']:
            # The API returns RFC3339 timestamps. Python can't handle RFC3339 timestamps natively,
            # so we have to use strptime and tack the UTC offset onto the input in order to produce
            # a timezone-aware datetime object
            creation_timestamp = datetime.datetime.strptime(c['creation_timestamp'] + "+00:00",
                                                            '%Y-%m-%dT%H:%M:%S.%fZ%z')

            cluster_list.append(Cluster(c['id'], c['name'], c['external_id'], creation_timestamp))

        return cluster_list
