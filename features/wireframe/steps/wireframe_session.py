"""In-memory simulator of the CV Studio wireframe prototype."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup, Tag

VIEW_TITLES = {
    "home": "Good morning, Ramon",
    "master": "Your source of truth",
    "tailor": "Tell us about the role",
    "match": "Choose your strongest evidence",
    "review": "Review your draft",
    "library": "Your career content",
    "versions": "Application-ready CVs",
    "personal-details": "Personal and contact details",
    "resume-import": "Bring in an existing resume",
    "questions": "Build evidence-backed answers",
    "assets": "Your visual identity",
    "mcp": "Use CV Studio with your assistant",
}

NAV_LABELS = {
    "home": "Home",
    "master": "Working Draft",
    "personal-details": "Personal details",
    "resume-import": "Import resume",
    "tailor": "Tailor",
    "questions": "Questions",
    "library": "Content library",
    "assets": "Assets",
    "versions": "Versions",
    "mcp": "Connect AI",
}


class WireframeSession:
    """Parse wireframe.html and mutate it like the prototype scripts would."""

    def __init__(self, html: str) -> None:
        """Load a BeautifulSoup document from wireframe HTML."""
        self.soup = BeautifulSoup(html, "html.parser")
        self.toast: Optional[str] = None
        self.active_view = "home"
        self._snippet_level = "standard"
        self._import_stage = "import-stage-file"
        self._selected_asset: Optional[str] = None
        self._asset_modal_open = False
        self._question_filter = "all"
        self._question_modal_open = False
        self._mcp_result: Optional[str] = None
        self._ensure_active("home")

    def _view(self, view_id: str) -> Tag:
        """Return the ``.view`` section for ``view_id``.

        The wireframe reuses some ids on buttons (e.g. ``#review``), so
        lookups must be scoped to ``section.view``.
        """
        view = self.soup.select_one(f"section.view#{view_id}")
        if view is None:
            raise AssertionError(f"unknown view: {view_id}")
        return view

    def _ensure_active(self, view_id: str) -> None:
        """Mark only ``view_id`` as the active view."""
        for view in self.soup.select("section.view"):
            classes = set(view.get("class", []))
            if view.get("id") == view_id:
                classes.add("active")
            else:
                classes.discard("active")
            view["class"] = sorted(classes)
        self.active_view = view_id
        title = self.soup.select_one("#title")
        if title is not None and view_id in VIEW_TITLES:
            title.string = VIEW_TITLES[view_id]

    def open_view(self, view_id: str) -> None:
        """Activate a named wireframe view."""
        self._view(view_id)
        self._ensure_active(view_id)

    def click_brand(self) -> None:
        """Return to the home view via the brand link."""
        self.open_view("home")

    def nav_labels(self) -> list[str]:
        """Return visible navigation destination labels."""
        labels: list[str] = []
        for button in self.soup.select("aside nav button"):
            span = button.select_one("span")
            text = (span.get_text(strip=True) if span else button.get_text(strip=True))
            if text:
                labels.append(text)
        return labels

    def view_text(self, view_id: Optional[str] = None) -> str:
        """Return the text content of a view (default: active)."""
        target = view_id or self.active_view
        return self._view(target).get_text(" ", strip=True)

    def page_title(self) -> str:
        """Return the sticky header title."""
        title = self.soup.select_one("#title")
        return title.get_text(strip=True) if title else ""

    def has_primary_action(self, label: str) -> bool:
        """True if a primary (or labelled) button with ``label`` exists."""
        needle = label.strip().lower()
        for button in self.soup.select("button"):
            if needle in button.get_text(" ", strip=True).lower():
                return True
        return False

    def click_primary(self, label: str) -> None:
        """Click a button whose label contains ``label`` and apply side effects."""
        needle = label.strip().lower()
        for button in self.soup.select("button"):
            text = button.get_text(" ", strip=True)
            if needle not in text.lower():
                continue
            self._handle_button(button, text)
            return
        raise AssertionError(f"no button labelled like {label!r}")

    def _handle_button(self, button: Tag, text: str) -> None:
        """Apply prototype side effects for a clicked button."""
        go = button.get("data-go")
        if go:
            self.open_view(go)
            return
        button_id = button.get("id") or ""
        if button_id == "analyze" or "analyze job posting" in text.lower():
            role = self.soup.select_one("#role")
            draft = self.soup.select_one("#draft-title")
            if role is not None and draft is not None:
                draft.string = role.get("value") or role.get_text(strip=True) or "Untitled CV"
            self.toast = "Job analyzed — 9 relevant snippets found"
            self.open_view("match")
            return
        if button_id == "review" or text.lower().startswith("review draft"):
            draft = self.soup.select_one("#draft-title")
            review = self.soup.select_one("#review-title")
            if draft is not None and review is not None:
                review.string = draft.get_text(strip=True)
            self.open_view("review")
            return
        if button_id == "save":
            self.toast = "Version saved (prototype only)"
            return
        if button_id == "export":
            self.toast = "PDF export would begin here"
            return
        if button_id == "upload-trigger" or "+ add asset" in text.lower():
            self._asset_modal_open = True
            modal = self.soup.select_one("#asset-modal")
            if modal is not None:
                classes = set(modal.get("class", []))
                classes.add("open")
                modal["class"] = sorted(classes)
            return
        if button_id == "save-details":
            self.toast = "Personal details saved (prototype only)"
            return
        if button_id == "add-profile":
            profile_list = self.soup.select_one("#profile-list")
            if profile_list is not None:
                row = self.soup.new_tag("div", **{"class": "profile-row"})
                row.string = "new profile"
                profile_list.append(row)
            return
        if "remove-profile" in (button.get("class") or []):
            row = button.find_parent(class_="profile-row")
            if row is not None:
                row.decompose()
            return
        if button_id == "complete-import":
            self.toast = "Resume imported successfully (prototype only)"
            return
        if button_id == "test-mcp":
            self._mcp_result = "✓ Prototype connection successful"
            result = self.soup.select_one("#test-result")
            if result is not None:
                result.string = self._mcp_result
            return
        if button_id in {"new-question-source", "add-source-link"}:
            self._question_modal_open = True
            modal = self.soup.select_one("#question-modal")
            if modal is not None:
                classes = set(modal.get("class", []))
                classes.add("open")
                modal["class"] = sorted(classes)
            return
        if go is None and "open master cv" in text.lower():
            self.open_view("review")

    def paste_posting(self, text: str) -> None:
        """Replace the job posting textarea contents."""
        posting = self.soup.select_one("#posting")
        if posting is None:
            raise AssertionError("job posting textarea missing")
        posting.clear()
        posting.append(text)
        count = self.soup.select_one("#count")
        if count is not None:
            count.string = f"{len(text)} characters"

    def analyze_posting(self) -> None:
        """Run the Analyze job posting action."""
        self.click_primary("Analyze job posting")

    def select_first_suggestion(self) -> None:
        """Ensure at least one suggestion checkbox is selected."""
        box = self.soup.select_one("#suggestions input[type=checkbox]")
        if box is None:
            # Wireframe pre-renders suggestions via JS; inject a stand-in.
            suggestions = self.soup.select_one("#suggestions")
            if suggestions is None:
                raise AssertionError("suggestions panel missing")
            label = self.soup.new_tag("label", **{"class": "suggestion selected"})
            checkbox = self.soup.new_tag("input", type="checkbox", checked="")
            label.append(checkbox)
            heading = self.soup.new_tag("h3")
            heading.string = "Cloud platform leadership"
            label.append(heading)
            suggestions.append(label)
            box = checkbox
        box["checked"] = ""
        selected = self.soup.select_one("#selected")
        if selected is not None:
            selected.string = "1"
        metric = self.soup.select_one("#metric")
        if metric is not None:
            metric.string = "1"

    def set_snippet_level(self, level: str) -> None:
        """Switch the first library card to a detail level."""
        card = self.soup.select_one(".variant-card")
        if card is None:
            raise AssertionError("no snippet cards")
        for button in card.select(".level-tabs button"):
            classes = set(button.get("class", []))
            if button.get("data-level") == level:
                classes.add("active")
            else:
                classes.discard("active")
            button["class"] = sorted(classes)
        copy = card.select_one(".variant-copy")
        attr = f"data-{level}"
        if copy is not None and card.has_attr(attr):
            copy.string = card[attr]
        self._snippet_level = level

    def first_snippet_copy(self) -> str:
        """Return the visible copy on the first snippet card."""
        copy = self.soup.select_one(".variant-card .variant-copy")
        return copy.get_text(strip=True) if copy else ""

    def first_snippet_attr(self, level: str) -> str:
        """Return a detail-level attribute from the first snippet card."""
        card = self.soup.select_one(".variant-card")
        if card is None:
            return ""
        return str(card.get(f"data-{level}", ""))

    def select_asset(self, name: str) -> None:
        """Select an asset card by name."""
        for card in self.soup.select(".asset-card[data-name]"):
            if card.get("data-name") == name:
                self._selected_asset = name
                inspector = self.soup.select_one("#inspector-name")
                if inspector is not None:
                    inspector.string = name
                detail = self.soup.select_one("#inspector-detail")
                if detail is not None:
                    classes = set(detail.get("class", []))
                    classes.add("open")
                    detail["class"] = sorted(classes)
                empty = self.soup.select_one("#inspector-empty")
                if empty is not None:
                    empty["style"] = "display:none"
                return
        raise AssertionError(f"asset not found: {name}")

    def set_first_name(self, value: str) -> None:
        """Update the personal-details first-name field and preview."""
        field = self.soup.select_one('[data-preview="first"]')
        if field is None:
            raise AssertionError("first name field missing")
        field["value"] = value
        preview = self.soup.select_one("#preview-first")
        if preview is not None:
            preview.string = value

    def profile_row_count(self) -> int:
        """Count social profile rows."""
        return len(self.soup.select("#profile-list .profile-row"))

    def remove_last_profile(self) -> None:
        """Remove the last social profile row."""
        rows = self.soup.select("#profile-list .profile-row")
        if not rows:
            raise AssertionError("no profile rows")
        rows[-1].decompose()

    def choose_resume(self, filename: str) -> None:
        """Simulate choosing a resume file and advancing import stages."""
        processing = self.soup.select_one("#processing-file")
        if processing is not None:
            processing.string = filename
        review = self.soup.select_one("#review-file-name")
        if review is not None:
            review.string = f"{filename} · ready to import"
        self._set_import_stage("import-stage-processing")
        self._set_import_stage("import-stage-review")

    def _set_import_stage(self, stage_id: str) -> None:
        """Activate an import wizard stage."""
        for stage in self.soup.select(".import-stage"):
            classes = set(stage.get("class", []))
            if stage.get("id") == stage_id:
                classes.add("active")
            else:
                classes.discard("active")
            stage["class"] = sorted(classes)
        self._import_stage = stage_id

    def import_stage_active(self, stage_id: str) -> bool:
        """True if the named import stage is active."""
        stage = self.soup.select_one(f"#{stage_id}")
        return bool(stage and "active" in stage.get("class", []))

    def filter_questions(self, label: str) -> None:
        """Filter question rows by status tab label."""
        mapping = {
            "all questions": "all",
            "needs work": "open",
            "complete": "complete",
        }
        key = mapping.get(label.strip().lower())
        if key is None:
            raise AssertionError(f"unknown question filter: {label}")
        self._question_filter = key
        for row in self.soup.select(".question-row"):
            status = row.get("data-status", "")
            hidden = key != "all" and status != key
            if hidden:
                row["hidden"] = ""
            elif row.has_attr("hidden"):
                del row["hidden"]

    def select_first_open_question(self) -> None:
        """Activate the first open question row."""
        for row in self.soup.select(".question-row"):
            if row.get("data-status") == "open":
                for other in self.soup.select(".question-row"):
                    classes = set(other.get("class", []))
                    classes.discard("active")
                    other["class"] = sorted(classes)
                classes = set(row.get("class", []))
                classes.add("active")
                row["class"] = sorted(classes)
                title = self.soup.select_one("#answer-title")
                if title is not None:
                    title.string = row.get("data-title", "")
                return
        raise AssertionError("no open questions")

    def visible_question_statuses(self) -> list[str]:
        """Return data-status values for non-hidden question rows."""
        statuses: list[str] = []
        for row in self.soup.select(".question-row"):
            if row.has_attr("hidden"):
                continue
            statuses.append(row.get("data-status", ""))
        return statuses

    def clone(self) -> "WireframeSession":
        """Return a deep copy of this session (unused helper)."""
        other = WireframeSession("<html></html>")
        other.soup = BeautifulSoup(str(self.soup), "html.parser")
        other.toast = self.toast
        other.active_view = self.active_view
        return other

    def wizard_step_current(self, view_id: str, step_number: int) -> bool:
        """True if the Nth step indicator in ``view_id`` is current (.on)."""
        view = self._view(view_id)
        steps = view.select(".steps > b")
        if step_number < 1 or step_number > len(steps):
            return False
        return "on" in steps[step_number - 1].get("class", [])
