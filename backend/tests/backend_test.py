"""Backend API tests for Roast My Startup."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://startup-truth-meter.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@roastmystartup.com"
ADMIN_PASSWORD = "roast2026!"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def created_roast(session):
    payload = {
        "startup_name": "TEST_RoastBot",
        "startup_description": "An AI-powered platform that delivers brutally honest startup feedback to founders who think they're the next unicorn but probably aren't.",
        "industry": "SaaS",
        "startup_website": "https://example.com",
        "startup_stage": "launched",
        "monthly_revenue": "5000",
        "roast_level": "reality",
    }
    r = session.post(f"{API}/roast", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- public endpoints ----------

class TestPublic:
    def test_root(self, session):
        r = session.get(f"{API}/")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_roast_levels(self, session):
        r = session.get(f"{API}/roast-levels")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        keys = {d["key"] for d in data}
        assert keys == {"friendly", "reality", "investor", "vcv"}
        for d in data:
            assert "label" in d and "tone" in d

    def test_example_roasts(self, session):
        r = session.get(f"{API}/example-roasts")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 6
        for ex in data:
            assert {"startup", "industry", "line", "score", "archetype"} <= set(ex.keys())


# ---------- roast generation ----------

class TestRoast:
    def test_create_roast_full_payload(self, created_roast):
        roast = created_roast
        # required top-level fields
        for k in [
            "roast_id", "score", "score_category", "level", "level_label",
            "dna", "archetype", "roast", "what_works", "what_needs_work",
            "investor_reaction", "reality_check", "high_impact_improvement", "best_line",
        ]:
            assert k in roast, f"missing {k}"
        # score range
        assert 0 <= roast["score"] <= 99
        # dna 6 fields
        dna_keys = {"clarity", "market_potential", "differentiation", "business_model", "positioning", "founder_delusion"}
        assert dna_keys <= set(roast["dna"].keys())
        # archetype
        assert "name" in roast["archetype"] and "description" in roast["archetype"]
        # roast object
        assert {"analogy", "investor_observation", "founder_joke", "practical_insight"} <= set(roast["roast"].keys())
        # lists
        assert isinstance(roast["what_works"], list) and len(roast["what_works"]) >= 1
        assert isinstance(roast["what_needs_work"], list) and len(roast["what_needs_work"]) >= 1

    def test_create_roast_validation_empty(self, session):
        r = session.post(f"{API}/roast", json={"startup_name": "", "startup_description": "", "industry": "", "roast_level": "reality"})
        assert r.status_code == 400

    def test_create_roast_invalid_level(self, session):
        r = session.post(f"{API}/roast", json={"startup_name": "X", "startup_description": "desc", "industry": "SaaS", "roast_level": "nuclear"})
        assert r.status_code == 400

    def test_get_roast_before_lead_capture(self, session):
        # create separate roast for this test
        payload = {"startup_name": "TEST_PreLead", "startup_description": "blah blah blah", "industry": "AI", "roast_level": "vcv"}
        r = session.post(f"{API}/roast", json=payload)
        assert r.status_code == 200
        rid = r.json()["roast_id"]
        g = session.get(f"{API}/roast/{rid}")
        assert g.status_code == 403


# ---------- leads ----------

class TestLeads:
    def test_lead_invalid_roast_id(self, session):
        r = session.post(f"{API}/leads", json={
            "roast_id": "non-existent-id",
            "full_name": "Test User",
            "email": "test@example.com",
            "biggest_challenge": "Distribution",
        })
        assert r.status_code == 404

    def test_lead_submit_unlocks_roast(self, session, created_roast):
        rid = created_roast["roast_id"]
        r = session.post(f"{API}/leads", json={
            "roast_id": rid,
            "full_name": "TEST Founder",
            "email": "TEST_founder@example.com",
            "linkedin_url": "https://linkedin.com/in/test",
            "startup_website": "https://example.com",
            "biggest_challenge": "Distribution",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["lead_priority"] in {"HIGH", "MEDIUM", "LOW"}

        # roast now accessible
        g = requests.get(f"{API}/roast/{rid}")
        assert g.status_code == 200
        data = g.json()
        assert data["roast_id"] == rid
        assert "score" in data and "dna" in data


# ---------- auth ----------

class TestAuth:
    def test_login_success(self, session):
        r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["email"] == ADMIN_EMAIL

    def test_login_wrong_password(self, session):
        r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpass"})
        assert r.status_code == 401

    def test_me_with_token(self, session, auth_headers):
        r = session.get(f"{API}/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_no_token(self, session):
        # use raw requests to avoid session auth header pollution
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------- admin ----------

class TestAdmin:
    def test_leads_requires_auth(self):
        r = requests.get(f"{API}/admin/leads")
        assert r.status_code == 401

    def test_leads_list(self, session, auth_headers, created_roast):
        r = session.get(f"{API}/admin/leads", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "leads" in body and "total" in body
        assert isinstance(body["leads"], list)
        assert body["total"] >= 1

    def test_leads_filter_priority(self, session, auth_headers):
        r = session.get(f"{API}/admin/leads?priority=HIGH", headers=auth_headers)
        assert r.status_code == 200
        for lead in r.json()["leads"]:
            assert lead["lead_priority"] == "HIGH"

    def test_leads_filter_level(self, session, auth_headers):
        r = session.get(f"{API}/admin/leads?roast_level=reality", headers=auth_headers)
        assert r.status_code == 200
        for lead in r.json()["leads"]:
            assert lead["roast_level"] == "reality"

    def test_leads_sort(self, session, auth_headers):
        r = session.get(f"{API}/admin/leads?sort_by=startup_score&order=desc", headers=auth_headers)
        assert r.status_code == 200
        leads = r.json()["leads"]
        if len(leads) >= 2:
            scores = [l["startup_score"] for l in leads]
            assert scores == sorted(scores, reverse=True)

    def test_stats(self, session, auth_headers):
        r = session.get(f"{API}/admin/stats", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for k in ["total_leads", "total_roasts", "high_priority", "medium_priority", "low_priority", "avg_score"]:
            assert k in body
        assert body["total_leads"] >= 1
        assert body["total_roasts"] >= 1

    def test_export_csv(self, session, auth_headers):
        r = session.get(f"{API}/admin/leads/export", headers=auth_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        assert "email" in body and "startup_name" in body
