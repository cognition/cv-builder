@app @import
Feature: Import a resume
  As a candidate
  I want to import an existing resume into the library
  So that I do not have to retype my history

  Scenario: Import resume route is shipped in the real app
    Given the CV Studio app is running
    When I open the "import" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the "import" nav item is marked active
    And the page title contains "Import"
