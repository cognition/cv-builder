@app @master
Feature: Master CV
  As a candidate
  I want a complete source CV
  So that tailored versions can start from a single foundation

  Background:
    Given the CV Studio app is running

  Scenario: Master CV opens the editable source document
    When I open the "master cv" page
    Then the response status is 200
    And the Master CV editor document is present

  Scenario: Person details API backs the editor
    When I GET the API path "/api/person"
    Then the response status is 200
    And the JSON response has field "first_name"
