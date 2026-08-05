"""Step definitions for wireframe-driven Cucumber/Behave features."""

from __future__ import annotations

from behave import given, then, when
from behave.runner import Context

from wireframe_session import WireframeSession


def _session(context: Context) -> WireframeSession:
    """Return the active wireframe session or fail clearly."""
    session = getattr(context, "wireframe", None)
    if session is None:
        raise AssertionError("wireframe is not loaded")
    return session


@given("the wireframe is loaded")
def step_load_wireframe(context: Context) -> None:
    """Parse cv/web/wireframe.html into a session."""
    html = context.wireframe_path.read_text(encoding="utf-8")
    context.wireframe = WireframeSession(html)


@when('I open the "{view}" view')
def step_open_view(context: Context, view: str) -> None:
    """Activate a wireframe view by id."""
    _session(context).open_view(view)


@when("I click the brand link")
def step_click_brand(context: Context) -> None:
    """Follow the brand link back to Home."""
    _session(context).click_brand()


@then("the navigation lists the following destinations")
@then("the navigation lists the following destinations:")
def step_nav_lists(context: Context) -> None:
    """Assert nav labels cover the expected destinations table."""
    assert context.table is not None
    expected = [row["destination"] for row in context.table]
    labels = _session(context).nav_labels()
    for name in expected:
        assert name in labels, f"missing nav destination: {name}; have {labels}"


@then('the "{view}" view is active')
def step_view_active(context: Context, view: str) -> None:
    """Assert the named view is the active one."""
    assert _session(context).active_view == view


@then('the page title contains "{fragment}"')
def step_title_contains(context: Context, fragment: str) -> None:
    """Assert the sticky header title contains a fragment."""
    title = _session(context).page_title()
    assert fragment.lower() in title.lower(), f"{fragment!r} not in {title!r}"


@then('I see a primary action labelled "{label}"')
def step_see_primary(context: Context, label: str) -> None:
    """Assert a button with the given label exists."""
    assert _session(context).has_primary_action(label), f"missing action {label!r}"


@then("I see a heading about building a focused CV")
def step_home_heading(context: Context) -> None:
    """Assert the home hero copy is present."""
    text = _session(context).view_text("home")
    assert "focused CV" in text or "focused cv" in text.lower()


@then('I see a "{heading}" section')
@then('I see a "{heading}" heading')
@then('I see an "{heading}" heading')
@then('I see an "{heading}" section')
def step_see_heading(context: Context, heading: str) -> None:
    """Assert a heading string appears in the active view."""
    text = _session(context).view_text()
    assert heading.lower() in text.lower(), f"{heading!r} not in view"


@then('I see a statistic for "{label}"')
def step_see_stat(context: Context, label: str) -> None:
    """Assert a home statistic label is present."""
    text = _session(context).view_text("home")
    assert label.lower() in text.lower()


@then("I see at least {count:d} version card")
@then("I see at least {count:d} version cards")
@then("I see at least {count:d} version row")
@then("I see at least {count:d} version rows")
@then("I see at least {count:d} snippet card")
@then("I see at least {count:d} snippet cards")
def step_see_count(context: Context, count: int) -> None:
    """Assert a minimum number of cards/rows for the active view."""
    session = _session(context)
    view = session.active_view
    if view == "home":
        found = len(session.soup.select("#home .cards article"))
    elif view == "versions":
        found = len(session.soup.select("#versions .version-list > p"))
    elif view == "library":
        found = len(session.soup.select("#library .variant-card"))
    else:
        found = 0
    assert found >= count, f"expected >= {count}, found {found}"


@when('I click the primary action "{label}"')
def step_click_primary(context: Context, label: str) -> None:
    """Click a labelled button."""
    _session(context).click_primary(label)


@then("the tailor wizard shows step {step:d} as current")
def step_wizard_step(context: Context, step: int) -> None:
    """Assert the current tailor wizard step indicator."""
    session = _session(context)
    view = session.active_view
    assert session.wizard_step_current(view, step), (
        f"step {step} is not current in view {view}"
    )


@then("I see a field for the version name")
def step_version_name_field(context: Context) -> None:
    """Assert the role/version name input exists."""
    assert _session(context).soup.select_one("#role") is not None


@then("I see a job posting textarea")
def step_posting_textarea(context: Context) -> None:
    """Assert the posting textarea exists."""
    assert _session(context).soup.select_one("#posting") is not None


@when('I paste a job posting about "{term1}" and "{term2}"')
def step_paste_posting(context: Context, term1: str, term2: str) -> None:
    """Paste a posting containing the given terms."""
    text = (
        f"We need someone experienced with {term1} who can lead "
        f"{term2} and deliver outcomes."
    )
    _session(context).paste_posting(text)


@when("I analyze the job posting")
def step_analyze(context: Context) -> None:
    """Click Analyze job posting."""
    _session(context).analyze_posting()


@given("I have analyzed a sample job posting")
def step_analyzed(context: Context) -> None:
    """Reach the match step with sample posting text."""
    if getattr(context, "wireframe", None) is None:
        html = context.wireframe_path.read_text(encoding="utf-8")
        context.wireframe = WireframeSession(html)
    session = _session(context)
    session.open_view("tailor")
    session.paste_posting(
        "cloud platforms and cross-functional teams delivering outcomes"
    )
    session.analyze_posting()


@then("I see suggested content to select")
def step_see_suggestions(context: Context) -> None:
    """Assert the suggestions panel exists (may be filled by analyze)."""
    session = _session(context)
    panel = session.soup.select_one("#suggestions")
    assert panel is not None
    session.select_first_suggestion()
    assert session.soup.select_one("#suggestions .suggestion") is not None


@when("I select at least 1 suggested snippet")
def step_select_snippet(context: Context) -> None:
    """Select a suggestion checkbox."""
    _session(context).select_first_suggestion()


@when("I review the draft")
def step_review_draft(context: Context) -> None:
    """Advance to the review step."""
    _session(context).click_primary("Review draft")


@then("I see a document outline")
def step_outline(context: Context) -> None:
    """Assert the review outline is present."""
    assert _session(context).soup.select_one(".outline") is not None


@given("I am on the review step of the tailor flow")
def step_on_review(context: Context) -> None:
    """Drive the tailor flow through to review."""
    step_analyzed(context)
    session = _session(context)
    session.select_first_suggestion()
    session.click_primary("Review draft")


@when("I save the version")
def step_save_version(context: Context) -> None:
    """Click Save version."""
    _session(context).click_primary("Save version")


@when("I export the PDF")
def step_export_pdf(context: Context) -> None:
    """Click Export PDF."""
    _session(context).click_primary("Export PDF")


@then("I see a confirmation toast")
def step_toast(context: Context) -> None:
    """Assert a toast message was set by the last action."""
    assert _session(context).toast, "expected a confirmation toast"


@then("I see a search field for snippets")
@then("I see a search field for assets")
def step_search_field(context: Context) -> None:
    """Assert a search input exists in the active view."""
    session = _session(context)
    assert session.soup.select_one("input.search, #asset-search") is not None


@then("each visible snippet card offers Brief, Standard, and Detailed levels")
def step_levels(context: Context) -> None:
    """Assert every variant card has the three level tabs."""
    cards = _session(context).soup.select(".variant-card")
    assert cards
    for card in cards:
        levels = {b.get("data-level") for b in card.select(".level-tabs button")}
        assert levels >= {"brief", "standard", "detailed"}


@when('I open the first snippet card\'s "{level}" level')
def step_open_level(context: Context, level: str) -> None:
    """Switch the first card to a detail level."""
    _session(context).set_snippet_level(level)


@then("that snippet card shows the brief copy")
def step_brief_copy(context: Context) -> None:
    """Assert visible copy matches the brief attribute."""
    session = _session(context)
    assert session.first_snippet_copy() == session.first_snippet_attr("brief")


@then("that snippet card shows the detailed copy")
def step_detailed_copy(context: Context) -> None:
    """Assert visible copy matches the detailed attribute."""
    session = _session(context)
    assert session.first_snippet_copy() == session.first_snippet_attr("detailed")


@then('I see a status pill of "{a}" or "{b}"')
def step_status_pill(context: Context, a: str, b: str) -> None:
    """Assert a READY or DRAFT status appears."""
    text = _session(context).view_text()
    assert a in text or b in text


@then('each version row has an "Open" action')
def step_open_actions(context: Context) -> None:
    """Assert every version row includes Open."""
    rows = _session(context).soup.select("#versions .version-list > p")
    assert rows
    for row in rows:
        assert "Open" in row.get_text(" ", strip=True)


@then("I see filter tabs for All, Photos, Logos, and Contact icons")
def step_asset_filters(context: Context) -> None:
    """Assert asset filter tabs exist."""
    labels = [
        b.get_text(strip=True)
        for b in _session(context).soup.select("[data-asset-filter]")
    ]
    for expected in ("All", "Photos", "Logos", "Contact icons"):
        assert expected in labels


@when('I select the asset named "{name}"')
def step_select_asset(context: Context, name: str) -> None:
    """Select an asset card."""
    _session(context).select_asset(name)


@then('the asset inspector shows "{name}"')
def step_inspector(context: Context, name: str) -> None:
    """Assert the inspector title."""
    node = _session(context).soup.select_one("#inspector-name")
    assert node is not None and name in node.get_text(strip=True)


@then("the add-asset modal is visible")
def step_asset_modal(context: Context) -> None:
    """Assert the asset modal is open."""
    session = _session(context)
    modal = session.soup.select_one("#asset-modal")
    assert modal is not None and "open" in modal.get("class", [])


@then("I can choose upload or URL as the source")
def step_asset_sources(context: Context) -> None:
    """Assert upload/URL source tabs exist."""
    sources = {
        b.get("data-source")
        for b in _session(context).soup.select("[data-source]")
    }
    assert "upload" in sources and "url" in sources


@then("I see a heading about using the CV library from an AI assistant")
def step_mcp_heading(context: Context) -> None:
    """Assert Connect AI hero copy."""
    text = _session(context).view_text("mcp")
    assert "AI assistant" in text or "assistant" in text.lower()


@then("I see a three-step setup guide")
def step_mcp_steps(context: Context) -> None:
    """Assert three setup steps are present."""
    steps = _session(context).soup.select("#mcp .setup-steps > li")
    assert len(steps) >= 3


@then("I see a copyable docker compose command")
def step_docker_cmd(context: Context) -> None:
    """Assert docker compose appears in Connect AI."""
    text = _session(context).view_text("mcp")
    assert "docker compose" in text.lower()


@then("I see an example assistant prompt")
def step_example_prompt(context: Context) -> None:
    """Assert an example prompt card exists."""
    assert _session(context).soup.select_one(".prompt-card") is not None


@when("I test the MCP connection")
def step_test_mcp(context: Context) -> None:
    """Click Test connection."""
    _session(context).click_primary("Test connection")


@then("I see a connection test result")
def step_mcp_result(context: Context) -> None:
    """Assert the MCP test result text was populated."""
    session = _session(context)
    result = session.soup.select_one("#test-result")
    assert result is not None and result.get_text(strip=True)


@then("I see fields for first name, last name, and professional headline")
def step_identity_fields(context: Context) -> None:
    """Assert identity inputs exist."""
    soup = _session(context).soup
    assert soup.select_one('[data-preview="first"]')
    assert soup.select_one('[data-preview="last"]')
    assert soup.select_one('[data-preview="headline"]')


@then("I see contact fields for email and phone")
def step_contact_fields(context: Context) -> None:
    """Assert contact inputs exist."""
    soup = _session(context).soup
    assert soup.select_one('[data-preview="email"]')
    assert soup.select_one('[data-preview="phone"]')


@then("I see a live preview of the contact block")
def step_live_preview(context: Context) -> None:
    """Assert the details preview aside exists."""
    assert _session(context).soup.select_one(".details-preview") is not None


@when('I set the first name to "{value}"')
def step_set_first(context: Context, value: str) -> None:
    """Update the first-name field."""
    _session(context).set_first_name(value)


@then('the live preview shows the first name "{value}"')
def step_preview_first(context: Context, value: str) -> None:
    """Assert preview first name."""
    node = _session(context).soup.select_one("#preview-first")
    assert node is not None and node.get_text(strip=True) == value


@when("I add a social profile")
def step_add_profile(context: Context) -> None:
    """Click + Add profile."""
    before = _session(context).profile_row_count()
    context.profile_count_before = before
    _session(context).click_primary("+ Add profile")


@then("a new profile row appears")
def step_profile_added(context: Context) -> None:
    """Assert profile row count increased."""
    before = getattr(context, "profile_count_before", 0)
    assert _session(context).profile_row_count() == before + 1


@when("I remove the last social profile")
def step_remove_profile(context: Context) -> None:
    """Remove the last profile row."""
    context.profile_count_before = _session(context).profile_row_count()
    _session(context).remove_last_profile()


@then("that profile row is gone")
def step_profile_gone(context: Context) -> None:
    """Assert profile row count decreased."""
    before = getattr(context, "profile_count_before", 1)
    assert _session(context).profile_row_count() == before - 1


@when("I save personal details")
def step_save_details(context: Context) -> None:
    """Click Save details."""
    _session(context).click_primary("Save details")


@then("the import wizard shows step {step:d} as current")
def step_import_step(context: Context, step: int) -> None:
    """Assert import step indicator."""
    steps = _session(context).soup.select(".import-steps > div")
    assert steps
    active = [i for i, node in enumerate(steps, start=1) if "active" in node.get("class", [])]
    assert step in active or (
        step == 1 and not any("active" in n.get("class", []) for n in steps[1:])
    )


@then("I see a drop zone for resume files")
def step_drop_zone(context: Context) -> None:
    """Assert the resume drop zone exists."""
    assert _session(context).soup.select_one("#resume-drop") is not None


@then("I can choose an import mode of new master CV, library, or compare")
def step_import_modes(context: Context) -> None:
    """Assert the three import mode radios exist."""
    values = {
        i.get("value")
        for i in _session(context).soup.select('input[name="import-mode"]')
    }
    assert values >= {"new", "library", "compare"}


@when('I choose a sample resume file named "{filename}"')
def step_choose_resume(context: Context, filename: str) -> None:
    """Simulate choosing a resume file."""
    _session(context).choose_resume(filename)


@then("the import processing stage becomes active")
def step_processing(context: Context) -> None:
    """Processing is reached during choose_resume; accept review too."""
    session = _session(context)
    assert session.import_stage_active("import-stage-processing") or session.import_stage_active(
        "import-stage-review"
    )


@then("eventually the import review stage is shown")
def step_import_review(context: Context) -> None:
    """Assert the review stage is active."""
    assert _session(context).import_stage_active("import-stage-review")


@then("I see extracted sections for Profile, Work experience, Skills, and Education")
def step_extracted(context: Context) -> None:
    """Assert extraction summary mentions the four sections."""
    text = _session(context).view_text("resume-import")
    for label in ("Profile", "Work experience", "Skills", "Education"):
        assert label in text


@given("I have a resume ready to review")
def step_resume_ready(context: Context) -> None:
    """Open import and advance to review."""
    if getattr(context, "wireframe", None) is None:
        html = context.wireframe_path.read_text(encoding="utf-8")
        context.wireframe = WireframeSession(html)
    session = _session(context)
    session.open_view("resume-import")
    session.choose_resume("sample-resume.pdf")


@when("I import the selected content")
def step_complete_import(context: Context) -> None:
    """Click Import selected content."""
    _session(context).click_primary("Import selected content")


@then("I see totals for answered, needs evidence, and not started")
def step_question_totals(context: Context) -> None:
    """Assert question stats copy is present."""
    text = _session(context).view_text("questions")
    for label in ("Answered", "Need evidence", "Not started"):
        assert label.lower() in text.lower()


@then("I see a list of question sources")
def step_question_sources(context: Context) -> None:
    """Assert the source list aside exists."""
    assert _session(context).soup.select_one(".source-list") is not None


@when("I select the first open question")
def step_select_question(context: Context) -> None:
    """Select the first open question."""
    _session(context).select_first_open_question()


@then("the answer workspace shows that question's title")
def step_answer_title(context: Context) -> None:
    """Assert answer title is populated."""
    title = _session(context).soup.select_one("#answer-title")
    assert title is not None and title.get_text(strip=True)


@then("I can edit the answer text")
def step_edit_answer(context: Context) -> None:
    """Assert the answer textarea exists."""
    assert _session(context).soup.select_one("#answer-copy") is not None


@then("I can link evidence from the library")
def step_link_evidence(context: Context) -> None:
    """Assert the link-evidence control exists."""
    assert _session(context).soup.select_one("#link-evidence") is not None


@when('I filter questions to "{label}"')
def step_filter_questions(context: Context, label: str) -> None:
    """Apply a question status filter."""
    _session(context).filter_questions(label)


@then("every visible question row needs work")
def step_rows_need_work(context: Context) -> None:
    """Assert visible rows are open."""
    statuses = _session(context).visible_question_statuses()
    assert statuses
    assert all(status == "open" for status in statuses)


@then("every visible question row is complete")
def step_rows_complete(context: Context) -> None:
    """Assert visible rows are complete."""
    statuses = _session(context).visible_question_statuses()
    assert statuses
    assert all(status == "complete" for status in statuses)


@when("I start adding a question source")
def step_add_source(context: Context) -> None:
    """Open the new question-source modal."""
    _session(context).click_primary("+ Add source")


@then("I can choose Job description, Questionnaire, or Competency matrix")
def step_source_types(context: Context) -> None:
    """Assert source-type buttons exist in the modal."""
    text = _session(context).soup.select_one("#question-modal").get_text(" ", strip=True)
    for label in ("Job description", "Questionnaire", "Competency matrix"):
        assert label in text
