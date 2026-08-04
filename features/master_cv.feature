@app @master
Feature: Master CV editor
  As a candidate
  I want to open the in-place master CV editor
  So that I can edit the source document used for exports

  Background:
    Given the CV Studio app is running

  Scenario: Master CV editor is reachable
    When I open the "master cv" page
    Then the response status is 200
    And the Master CV editor document is present

  Scenario: Person details API backs the editor
    When I GET the API path "/api/person"
    Then the response status is 200
    And the JSON response has field "first_name"
