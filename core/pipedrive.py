"""Lekki klient Pipedrive API (token z ustawień/secrets)."""
import requests

BASE = "https://api.pipedrive.com/v1"
TIMEOUT = 20


class PipedriveClient:
    def __init__(self, api_token: str):
        self.token = api_token

    def _get(self, path, **params):
        params["api_token"] = self.token
        r = requests.get(BASE + path, params=params, timeout=TIMEOUT)
        j = r.json()
        if not j.get("success"):
            raise RuntimeError(j.get("error") or "Pipedrive: błąd %s" % r.status_code)
        return j.get("data")

    def test(self):
        me = self._get("/users/me")
        return me.get("name"), me.get("company_name")

    def search_orgs(self, term):
        data = self._get("/itemSearch", term=term, item_types="organization", limit=15) or {}
        return [i["item"] for i in data.get("items", [])]

    def search_persons(self, term):
        data = self._get("/itemSearch", term=term, item_types="person", limit=15) or {}
        return [i["item"] for i in data.get("items", [])]

    def org(self, org_id):
        return self._get("/organizations/%s" % org_id)

    def org_deals(self, org_id, status="all_not_deleted"):
        return self._get("/organizations/%s/deals" % org_id, status=status, limit=30) or []

    def deal_mail_messages(self, deal_id):
        return self._get("/deals/%s/mailMessages" % deal_id, limit=20) or []

    def mail_body(self, message_id):
        d = self._get("/mailbox/mailMessages/%s" % message_id, include_body=1) or {}
        return d

    def upload_file(self, deal_id, filepath, name=None):
        with open(filepath, "rb") as f:
            r = requests.post(
                BASE + "/files", params={"api_token": self.token},
                data={"deal_id": deal_id},
                files={"file": (name or str(filepath).split("/")[-1], f, "application/pdf")},
                timeout=60)
        j = r.json()
        if not j.get("success"):
            raise RuntimeError(j.get("error") or "Błąd wysyłki pliku")
        return j["data"]

    def list_pipelines(self):
        return self._get("/pipelines") or []

    def list_persons_of_org(self, org_id):
        return self._get("/organizations/%s/persons" % org_id) or []

    def create_deal(self, title, value=None, currency="PLN", org_id=None,
                    person_id=None, pipeline_id=None):
        data = {"title": title, "currency": currency}
        if value is not None:
            data["value"] = value
        if org_id:
            data["org_id"] = org_id
        if person_id:
            data["person_id"] = person_id
        if pipeline_id:
            data["pipeline_id"] = pipeline_id
        r = requests.post(BASE + "/deals", params={"api_token": self.token},
                          data=data, timeout=TIMEOUT)
        j = r.json()
        if not j.get("success"):
            raise RuntimeError(j.get("error") or "Nie udało się utworzyć szansy")
        return j["data"]
