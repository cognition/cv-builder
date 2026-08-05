@app @master
Feature: Master CV
  As a candidate
  I want a complete source CV inside CV Studio
  So that I can edit it without losing the app navigation

  Background:
    Given the CV Studio app is running

  Scenario: Master CV opens inside the Studio shell
    When I open the "master cv" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the "master" nav item is marked active
    And the page title contains "Master"
    And the Master CV editor document is present
    And the page has an element matching ".cv-document.edit-mode"
    And the page has an element matching "header #btn-save"
    And the page has an element matching "#preview-pane"

  Scenario: Person details API backs the editor
    When I GET the API path "/api/person"
    Then the response status is 200
    And the JSON response has field "first_name"

