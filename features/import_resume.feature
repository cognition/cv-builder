@app @import
Feature: Import a resume
  As a candidate
  I want to bring an existing resume into CV Studio
  So that I can turn it into editable, reusable content

  Background:
    Given the CV Studio app is running

  Scenario: Import starts at file selection
    When I open the "import" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the "import" nav item is marked active
    And the page heading contains "Import a resume"
    And the page has an element matching "#resume-drop"
    And the page has an element matching "#resume-file"
    And the page has an element matching "#step-file.active"
    And the page contains "Add content to the library"
    And the import mode "library" is available
    And the import mode "library" is selected
    And the import mode "new" is available
    And the import mode "compare" is disabled

  Scenario: Upload and confirm import via the API
    When I upload a sample resume text file via the API
    Then the response status is 201
    And the JSON response has field "token"
    And the JSON response has field "candidates"
    When I confirm the staged import via the API
    Then the response status is 200
    And the JSON response has field "snippet_count"
    And the imports list is non-empty

  Scenario: Master confirm rewrites content sections and preserves person
    Given a staged sample resume upload
    When I confirm the import with mode "master"
    Then the response status is 200
    And the master CV person first name is unchanged
    And the master CV has non-empty bio content
    And the import created library snippets

  @wip
  Scenario: Browser wizard advances through extraction stages
    # Requires driving import.js (file picker + staged UI transitions).
    When I open the "import" page
    Then the page has an element matching "#stage-review"
