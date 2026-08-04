@app @library
Feature: Content library
  As a candidate
  I want to browse reusable career snippets at multiple detail levels
  So that I can reuse evidence across tailored CVs

  Background:
    Given the CV Studio app is running

  Scenario: Library page exposes browse chrome
    When I open the "content library" page
    Then the response status is 200
    And the "library" nav item is marked active
    And the page heading contains "Content library"
    And the page has an element matching "#filter-search"
    And the page has an element matching "#library-grid"
    And the page has an element matching "#btn-new-snippet"
    And the page contains "brief, standard, and detailed"

  Scenario: Snippets API returns seeded library content
    When I GET the API path "/api/snippets"
    Then the response status is 200
    And the JSON response is a non-empty list

  Scenario: A new snippet can be created through the API
    When I create a library snippet via the API
    Then the response status is 201

  @wip
  Scenario: Browser UI switches a snippet between detail levels
    # Requires driving library.js card rendering and level tabs.
    When I open the "content library" page
    Then the page has an element matching "#library-grid"
