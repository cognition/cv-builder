@app @tailor
Feature: Tailor a CV to a job posting
  As a candidate
  I want to paste a job posting and choose matching evidence
  So that I can export a focused application CV

  Background:
    Given the CV Studio app is running

  Scenario: Tailor collects job details and draft controls
    When I open the "tailor" page
    Then the response status is 200
    And the "tailor" nav item is marked active
    And the page heading contains "What role are you applying for"
    And the page has an element matching "#variant-name"
    And the page has an element matching "#posting-text"
    And the page has an element matching "#btn-match"
    And the page has an element matching "#btn-compose"
    And the page has an element matching "#suggestions"
    And the page has an element matching "#draft-list"

  Scenario: Match API ranks snippets against a posting
    When I POST JSON to "/api/match" with
      """
      {
        "text": "Looking for Python leadership, delivery, and stakeholder communication experience",
        "limit": 10
      }
      """
    Then the response status is 200
    And the JSON response is a non-empty list
    And the first match result has field "snippet_id"
    And the first match result has field "matched_terms"

  Scenario: Compose API builds a named variant from matched content
    When I compose a CV variant via the API using the first matched snippet
    Then the response status is 200
    And the composed variant appears in the variants API

  @wip
  Scenario: Browser UI selects suggestions and previews the PDF
    # Requires driving tailor.js (match click, checkbox selection, preview pane).
    When I open the "tailor" page
    Then the page has an element matching "#preview-frame"
