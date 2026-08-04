@app @library
Feature: Content library
  As a candidate
  I want a browsable snippet library backed by SQLite
  So that I can reuse brief, standard, and detailed evidence

  Background:
    Given the CV Studio app is running

  Scenario: Library page renders browse chrome
    When I open the "content library" page
    Then the response status is 200
    And the "library" nav item is marked active
    And the page heading contains "Content library"
    And the page has an element matching "#library-grid"
    And the page has an element matching "#btn-new-snippet"

  Scenario: Snippets API returns seeded library content
    When I GET the API path "/api/snippets"
    Then the response status is 200
    And the JSON response is a non-empty list

  Scenario: A new snippet can be created through the API
    When I create a library snippet via the API
    Then the response status is 201
