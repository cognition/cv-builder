@app @versions
Feature: CV versions
  As a candidate
  I want to browse composed CV versions
  So that I can reopen application-ready documents

  Background:
    Given the CV Studio app is running

  Scenario: Versions page is reachable in the shell
    When I open the "versions" page
    Then the response status is 200
    And the "versions" nav item is marked active
    And the page heading contains "CV versions"
    And the page has an element matching "#version-list"
    And the page has an element matching "a.primary[href='/cv/web/build']"

  Scenario: Variants API lists composed documents
    When I GET the API path "/api/variants"
    Then the response status is 200
    And the JSON response is a list
