@app @tailor
Feature: Tailor a CV to a job posting
  As a candidate
  I want to paste a posting, rank snippets, and compose a version
  So that I can produce a focused application CV

  Background:
    Given the CV Studio app is running

  Scenario: Tailor page exposes posting and draft controls
    When I open the "tailor" page
    Then the response status is 200
    And the "tailor" nav item is marked active
    And the page heading contains "What role are you applying for"
    And the page has an element matching "#posting-text"
    And the page has an element matching "#btn-match"
    And the page has an element matching "#btn-compose"

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
