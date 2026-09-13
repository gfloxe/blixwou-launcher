import json
import pytest
import requests
from blixwou.auth import api
from blixwou.config import LauncherError
from blixwou.callback_page import callback_page


@pytest.mark.parametrize("url,status,payload,expected", [
    ("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", 400, {"error_description": "AADSTS7000218: confidential secret user@example.com"}, "client confidentiel"),
    ("https://xsts.auth.xboxlive.com/xsts/authorize", 401, {"XErr": 2148916233}, "profil Xbox"),
    ("https://api.minecraftservices.com/authentication/login_with_xbox", 401, {"errorMessage": "Invalid app registration, see AppRegInfo"}, "demander l’accès"),
    ("https://user.auth.xboxlive.com/user/authenticate", 401, {"secret": "private-token"}, "Xbox Live"),
])
def test_safe_actionable_provider_errors(monkeypatch, url, status, payload, expected):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode()
    def fail(*args, **kwargs):
        raise requests.HTTPError(response=response)
    monkeypatch.setattr("blixwou.auth.request", fail)
    with pytest.raises(LauncherError) as error:
        api("POST", url)
    assert expected in str(error.value)
    assert "HTTP " + str(status) in str(error.value)
    assert "private-token" not in str(error.value)
    assert "user@example.com" not in str(error.value)


def test_callback_is_self_contained_and_does_not_claim_login_success():
    page = callback_page().decode()
    assert 'lang="fr"' in page and "data:image/png;base64," in page
    assert "vérifie maintenant" in page
    assert "history.replaceState" in page
    assert "Connexion réussie" not in page
    assert "Ce lien a expiré" in callback_page("invalid").decode()
    assert "Connexion interrompue" in callback_page("cancelled").decode()
