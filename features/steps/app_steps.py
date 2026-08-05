"""Step definitions for the real CV Studio Flask app (not the wireframe)."""

from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any, Optional

from behave import given, then, when
from behave.runner import Context

from app_client import (
    NAV_ACTIVE,
    api_json,
    has_selector,
    has_text,
    nav_labels,
    open_page,
    page,
    resolve_path,
)


@given("the CV Studio app is running")
def step_app_running(context: Context) -> None:
    """Assert the Flask test client was initialised."""
    assert context.client is not None, "Flask client was not initialised"


@when('I open the "{name}" page')
def step_open_page(context: Context, name: str) -> None:
    """GET a named product page from the real app."""
    open_page(context, name)
    context.last_response = context.response


@when('I request the app path "{path}"')
def step_request_path(context: Context, path: str) -> None:
    """GET a raw path from the Flask test client."""
    response = context.client.get(path)
    context.response = response
    context.last_response = response
    context.page_html = response.get_data(as_text=True)
    from bs4 import BeautifulSoup

    context.page = BeautifulSoup(context.page_html, "html.parser")
    context.page_path = path


@then("the response status is {code:d}")
def step_status(context: Context, code: int) -> None:
    """Assert the last HTTP status code."""
    response = context.response or context.last_response
    assert response is not None, "no response captured"
    assert response.status_code == code, (
        f"expected {code}, got {response.status_code}"
    )


@then("the page contains the app shell navigation")
def step_has_shell(context: Context) -> None:
    """Assert the shared shell brand and nav are present."""
    soup = page(context)
    assert has_text(soup, "CV Studio"), "brand text missing"
    assert has_selector(soup, "aside nav a.nav-link"), "shell nav links missing"


@then('the "{active}" nav item is marked active')
def step_nav_active(context: Context, active: str) -> None:
    """Assert the shell marks the expected destination active."""
    soup = page(context)
    active_link = soup.select_one("a.nav-link.active")
    assert active_link is not None, "no active nav-link found"
    key = NAV_ACTIVE.get(active.lower(), active.lower())
    href = active_link.get("href", "")
    expected = resolve_path(key if key in NAV_ACTIVE.values() else active)
    # NAV_ACTIVE maps labels → keys; resolve_path wants page names.
    expected_by_key = {
        "home": "/cv/web/",
        "master": "/cv/web/edit",
        "details": "/cv/web/details",
        "import": "/cv/web/import",
        "tailor": "/cv/web/build",
        "questions": "/cv/web/questions",
        "library": "/cv/web/library",
        "assets": "/cv/web/assets",
        "versions": "/cv/web/variants",
        "connect": "/cv/web/connect",
    }
    want = expected_by_key.get(active.lower(), expected)
    assert href == want or href.rstrip("/") == want.rstrip("/"), (
        f"active nav href={href!r}, expected {want!r} for {active!r}"
    )


@then("the page notes that it is sample data only")
def step_sample_note(context: Context) -> None:
    """Assert the wireframe prototype disclaimer is present."""
    html = (context.page_html or "").lower()
    assert "sample data" in html, "wireframe sample-data note missing"


@then("the navigation lists the following destinations")
def step_nav_lists(context: Context) -> None:
    """Assert shell nav labels match the table."""
    soup = page(context)
    labels = nav_labels(soup)
    expected = [row["destination"] for row in context.table]
    for item in expected:
        assert item in labels, f"nav missing {item!r}; have {labels}"


@then('the page title contains "{fragment}"')
def step_title_contains(context: Context, fragment: str) -> None:
    """Assert the HTML title or header contains a fragment."""
    soup = page(context)
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.select_one("main header h1")
    header = h1.get_text(" ", strip=True) if h1 else ""
    blob = f"{title} {header}"
    assert fragment.lower() in blob.lower(), (
        f"{fragment!r} not in title/header {blob!r}"
    )


@then('the page heading contains "{fragment}"')
def step_heading_contains(context: Context, fragment: str) -> None:
    """Assert an h1/h2 on the page contains a fragment."""
    soup = page(context)
    headings = " ".join(h.get_text(" ", strip=True) for h in soup.select("h1, h2"))
    assert fragment.lower() in headings.lower(), (
        f"{fragment!r} not in headings {headings!r}"
    )


@then('the page contains "{fragment}"')
def step_page_contains(context: Context, fragment: str) -> None:
    """Assert visible page text contains a fragment."""
    assert has_text(page(context), fragment), f"{fragment!r} not found on page"


@then('the page has an element matching "{selector}"')
def step_has_element(context: Context, selector: str) -> None:
    """Assert a CSS selector matches."""
    assert has_selector(page(context), selector), f"selector {selector!r} not found"


@then('the import mode "{mode}" is available')
def step_import_mode_available(context: Context, mode: str) -> None:
    """Assert an import mode radio exists and can be selected."""
    radio = page(context).select_one(f'input[name="import-mode"][value="{mode}"]')
    assert radio is not None, f"import mode {mode!r} not found"
    assert not radio.has_attr("disabled"), f"import mode {mode!r} is disabled"


@then('the import mode "{mode}" is disabled')
def step_import_mode_disabled(context: Context, mode: str) -> None:
    """Assert an import mode radio exists but is disabled."""
    radio = page(context).select_one(f'input[name="import-mode"][value="{mode}"]')
    assert radio is not None, f"import mode {mode!r} not found"
    assert radio.has_attr("disabled"), f"import mode {mode!r} is enabled"


@then('the import mode "{mode}" is selected')
def step_import_mode_selected(context: Context, mode: str) -> None:
    """Assert an import mode radio is checked by default."""
    radio = page(context).select_one(f'input[name="import-mode"][value="{mode}"]')
    assert radio is not None, f"import mode {mode!r} not found"
    assert radio.has_attr("checked"), f"import mode {mode!r} is not selected"


@then("the Master CV editor document is present")
def step_master_editor(context: Context) -> None:
    """Assert the CV document editor (template or shell-wrapped body) rendered."""
    soup = page(context)
    if has_selector(soup, ".cv-document"):
        assert has_selector(soup, ".cv-document.edit-mode") or has_selector(
            soup, ".cv-document [contenteditable='true']"
        ), "master CV document shell missing edit-mode or contenteditable"
        return
    html = context.page_html or ""
    assert (
        "edit-mode" in html.lower()
        or "contenteditable" in html.lower()
        or ("person" in html.lower() and "experience" in html.lower())
    ), "master CV editor markup missing"


@when('I GET the API path "{path}"')
def step_get_api(context: Context, path: str) -> None:
    """GET a JSON API endpoint."""
    api_json(context, "get", path)
    context.last_response = context.response


@when('I POST JSON to "{path}" with')
def step_post_json(context: Context, path: str) -> None:
    """POST a JSON body from a docstring or table."""
    payload = _payload_from_context(context)
    api_json(context, "post", path, payload)
    context.last_response = context.response


@when('I PUT JSON to "{path}" with')
def step_put_json(context: Context, path: str) -> None:
    """PUT a JSON body from a docstring or table."""
    payload = _payload_from_context(context)
    api_json(context, "put", path, payload)
    context.last_response = context.response


@when('I DELETE the API path "{path}"')
def step_delete_api(context: Context, path: str) -> None:
    """DELETE a JSON API endpoint."""
    api_json(context, "delete", path)
    context.last_response = context.response


@then("the JSON response is a non-empty list")
def step_json_list(context: Context) -> None:
    """Assert the last JSON body is a non-empty list."""
    body = context.response_json
    assert isinstance(body, list) and body, f"expected non-empty list, got {body!r}"


@then("the JSON response is a list")
def step_json_list_any(context: Context) -> None:
    """Assert the last JSON body is a list (may be empty)."""
    assert isinstance(context.response_json, list), (
        f"expected list, got {type(context.response_json)}"
    )


@then('the JSON response has field "{field}"')
def step_json_has_field(context: Context, field: str) -> None:
    """Assert a top-level JSON object field exists."""
    body = context.response_json
    assert isinstance(body, dict), f"expected object, got {body!r}"
    assert field in body, f"missing field {field!r} in {body!r}"


@then('the first match result has field "{field}"')
def step_first_match_field(context: Context, field: str) -> None:
    """Assert the first ranked match includes a field."""
    body = context.response_json
    assert isinstance(body, list) and body, "expected ranked matches"
    assert field in body[0], f"missing {field!r} in {body[0]!r}"


@when("I create a library snippet via the API")
def step_create_snippet(context: Context) -> None:
    """POST a disposable snippet for later assertions."""
    payload = {
        "category": "skill",
        "heading": "BDD Temp Skill",
        "tags": ["bdd", "temp"],
        "variants": {"standard": "Temporary snippet created by Behave."},
    }
    body = api_json(context, "post", "/api/snippets", payload)
    context.last_response = context.response
    assert context.response.status_code in {200, 201}, body
    context.created_snippet_id = body.get("id") or body.get("snippet_id")
    assert context.created_snippet_id, f"no snippet id in {body!r}"


@when("I create a question source via the API")
def step_create_source(context: Context) -> None:
    """POST a disposable question source with pasted questions."""
    payload = {
        "title": "BDD Sample Form",
        "source_type": "form",
        "text": (
            "1. Describe a time you led a delivery team.\n"
            "2. How do you approach stakeholder communication?"
        ),
    }
    body = api_json(context, "post", "/api/question-sources", payload)
    context.last_response = context.response
    assert context.response.status_code in {200, 201}, body
    context.created_source_id = body.get("id") or body.get("source_id")
    assert context.created_source_id, f"no source id in {body!r}"


@then("the question sources list includes the created source")
def step_sources_include_created(context: Context) -> None:
    """GET question sources and find the created one."""
    body = api_json(context, "get", "/api/question-sources")
    context.last_response = context.response
    assert context.response.status_code == 200
    ids = {item.get("id") for item in body}
    assert context.created_source_id in ids, f"{context.created_source_id} not in {ids}"


@then("the questions list is non-empty")
def step_questions_nonempty(context: Context) -> None:
    """GET /api/questions and require at least one row."""
    body = api_json(context, "get", "/api/questions")
    context.last_response = context.response
    assert isinstance(body, list) and body, f"expected questions, got {body!r}"


@when("I compose a CV variant via the API using the first matched snippet")
def step_compose_from_match(context: Context) -> None:
    """Match a posting, then compose a named variant from the top hit."""
    matches = api_json(
        context,
        "post",
        "/api/match",
        {"text": "Python leadership delivery stakeholder communication", "limit": 5},
    )
    assert context.response.status_code == 200 and matches, matches
    top = matches[0]
    snippet_id = top.get("snippet_id") or (top.get("snippet") or {}).get("id")
    assert snippet_id, f"no snippet id in match {top!r}"
    detail_level = _preferred_detail_level(top)
    name = "bdd-compose-demo"
    context.compose_name = name
    body = api_json(
        context,
        "post",
        "/api/compose",
        {
            "name": name,
            "selections": [
                {
                    "snippet_id": snippet_id,
                    "detail_level": detail_level,
                }
            ],
        },
    )
    context.last_response = context.response
    assert context.response.status_code == 200, body


@then("the composed variant appears in the variants API")
def step_variant_listed(context: Context) -> None:
    """Assert the composed variant name is listed."""
    body = api_json(context, "get", "/api/variants")
    context.last_response = context.response
    names = {item.get("name") for item in body}
    assert context.compose_name in names, f"{context.compose_name!r} not in {names}"


@then("the home page reports a snippet count")
def step_home_snippet_count(context: Context) -> None:
    """Assert the home stats strip shows a numeric snippet count."""
    soup = page(context)
    stats = soup.select_one(".stats")
    assert stats is not None, "home stats missing"
    text = stats.get_text(" ", strip=True)
    assert re.search(r"\d+", text), f"no numeric count in {text!r}"
    assert "snippet" in text.lower()


@then("the home page reports a versions count")
def step_home_versions_count(context: Context) -> None:
    """Assert the home stats strip shows a CV versions count."""
    soup = page(context)
    stats = soup.select_one(".stats")
    assert stats is not None, "home stats missing"
    text = stats.get_text(" ", strip=True)
    assert "version" in text.lower(), f"versions stat missing in {text!r}"


@when("I upload a sample resume text file via the API")
def step_upload_resume(context: Context) -> None:
    """POST a multipart sample resume to ``/api/imports``."""
    sample = (
        "Jordan Rivers\n\n"
        "Summary\n"
        "Platform leader with a decade of experience building resilient cloud systems.\n\n"
        "Experience\n"
        "Staff Platform Engineer — Acme Corp (2021 - Present)\n"
        "- Led migration of 40+ services to Kubernetes\n"
        "- Built the on-call incident response program\n\n"
        "Skills\n"
        "Kubernetes, Terraform, AWS\n\n"
        "Education\n"
        "BSc Computer Science, State University, 2013\n"
    )
    response = context.client.post(
        "/api/imports",
        data={"file": (BytesIO(sample.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )
    context.response = response
    context.last_response = response
    context.response_json = response.get_json()
    if isinstance(context.response_json, dict):
        context.import_token = context.response_json.get("token")


@given("a staged sample resume upload")
def step_stage_sample_resume_upload(context: Context) -> None:
    """Stage a sample resume and capture master-person state before confirm."""
    sample = (
        "Summary\n"
        "Platform leader.\n\n"
        "Experience\n"
        "Engineer - Acme\n"
        "- Built things\n\n"
        "Skills\n"
        "Python\n\n"
        "Education\n"
        "BSc\n"
    )
    response = context.client.post(
        "/api/imports",
        data={"file": (BytesIO(sample.encode("utf-8")), "resume.txt")},
        content_type="multipart/form-data",
    )
    context.response = response
    context.last_response = response
    context.response_json = response.get_json()
    assert response.status_code == 201, context.response_json
    assert isinstance(context.response_json, dict), context.response_json
    context.import_token = context.response_json.get("token")
    assert context.import_token, f"no import token in {context.response_json!r}"

    person_response = context.client.get("/api/person")
    context.person_before = person_response.get_json()
    assert isinstance(context.person_before, dict), context.person_before


@when("I confirm the staged import via the API")
def step_confirm_import(context: Context) -> None:
    """Confirm the staged import token created by the previous step."""
    assert context.import_token, "no import token — upload a resume first"
    body = api_json(
        context, "post", f"/api/imports/{context.import_token}/confirm", {}
    )
    context.last_response = context.response
    if isinstance(body, dict):
        context.import_id = body.get("id")


@when('I confirm the import with mode "{mode}"')
def step_confirm_import_with_mode(context: Context, mode: str) -> None:
    """Confirm the staged import token using an explicit import mode."""
    assert context.import_token, "no import token - upload a resume first"
    body = api_json(
        context,
        "post",
        f"/api/imports/{context.import_token}/confirm",
        {"mode": mode},
    )
    context.last_response = context.response
    if isinstance(body, dict):
        context.import_id = body.get("id")


@then("the imports list is non-empty")
def step_imports_nonempty(context: Context) -> None:
    """GET /api/imports and require at least one record."""
    body = api_json(context, "get", "/api/imports")
    context.last_response = context.response
    assert isinstance(body, list) and body, f"expected imports, got {body!r}"


@then("the master CV person first name is unchanged")
def step_master_person_first_name_unchanged(context: Context) -> None:
    """Assert master import preserves existing person details."""
    after = context.client.get("/api/person").get_json()
    assert isinstance(after, dict), after
    assert after["first_name"] == context.person_before["first_name"]


@then("the master CV has non-empty bio content")
def step_master_bio_nonempty(context: Context) -> None:
    """Assert master import wrote non-empty biography content."""
    import cvweb

    data = cvweb.load_data()
    assert data.get("bio"), "expected imported bio content"


@then("the import created library snippets")
def step_import_created_library_snippets(context: Context) -> None:
    """Assert master import also created reusable library snippets."""
    body = context.response_json
    assert isinstance(body, dict), body
    assert body["snippet_count"] > 0


def _preferred_detail_level(match: dict[str, Any]) -> str:
    """Pick a detail level that exists on the matched snippet."""
    preferred = ("standard", "detailed", "brief")
    snippet = match.get("snippet") if isinstance(match.get("snippet"), dict) else {}
    variants = snippet.get("variants") if isinstance(snippet, dict) else None
    available: list[str] = []
    if isinstance(variants, dict):
        available = [level for level, content in variants.items() if content]
    elif isinstance(variants, list):
        available = [
            str(item.get("detail_level"))
            for item in variants
            if isinstance(item, dict) and item.get("detail_level")
        ]
    explicit = match.get("detail_level")
    if explicit and (not available or explicit in available):
        return str(explicit)
    for level in preferred:
        if level in available:
            return level
    return available[0] if available else "standard"


def _payload_from_context(context: Context) -> dict[str, Any]:
    """Build a JSON payload from a Gherkin docstring or key/value table."""
    if context.text:
        return json.loads(context.text)
    if context.table is None:
        return {}
    payload: dict[str, Any] = {}
    for row in context.table:
        key = row[0] if "key" not in row.headings else row["key"]
        value: Any = row[1] if "value" not in row.headings else row["value"]
        if isinstance(value, str) and (
            value.startswith("{") or value.startswith("[")
        ):
            value = json.loads(value)
        elif isinstance(value, str) and value.isdigit():
            value = int(value)
        payload[key] = value
    return payload
