# -*- coding: utf-8 -*-
import jwt
import requests


class UnifiedHybridClient:
    """
    Limited access to the UHC API for authentication and cluster searching
    """

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
        ot_decoded = jwt.decode(
            self.offline_token,
            self.public_key,
            algorithms="RS256",
            verify=(self.public_key is not None),
        )
        self.iss_url = ot_decoded["iss"]
        self.client_id = ot_decoded["aud"]

    def __get_access_token(self) -> str:
        """
        Obtain a short-lived access token from the SSO service

        :returns: (str) a short-lived access token
        """
        response = requests.post(
            "{}/protocol/openid-connect/token".format(self.iss_url),
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.offline_token,
            },
            headers={"accept": "application/json"},
        )
        return response.json()["access_token"]

    def search_clusters(self, query: str) -> dict:
        """
        Query a list of clusters from the UHC HTTP API.

        :param query: (str) Specifies the search criteria. This syntax of
            this parameter is similar to the syntax of the WHERE clause of
            an SQL statement, but using the names of the attributes of the
            cluster instead of the names of the columns of a table.
        :returns: (dict) the response from the API in dict format
        """
        response = requests.get(
            "{}/api/clusters_mgmt/v1/clusters".format(self.api_url),
            verify=True,
            headers={
                "accept": "application/json",
                "Authorization": "Bearer " + self.__get_access_token(),
            },
            params={"search": query},
        )
        if response.status_code == 200:
            data = response.json()
        else:
            raise Exception(
                "HTTP Status Code {} ({})".format(
                    response.status_code, response.content
                )
            )

        return data
