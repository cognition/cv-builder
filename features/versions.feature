@app @versions
Feature: CV versions
  As a candidate
  I want to see drafts and exported application documents
  So that I can reopen or continue a tailored CV

  Background:
    Given the CV Studio app is running

  Scenario: Versions page exposes list chrome and new-CV action
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

  Scenario: A composed variant appears after tailor compose
    When I compose a CV variant via the API using the first matched snippet
    Then the composed variant appears in the variants API

  @wip
  Scenario: Browser UI lists version rows with Open actions
    # Requires driving versions.js against populated variant data.
    When I open the "versions" page
    Then the page has an element matching "#version-list"
