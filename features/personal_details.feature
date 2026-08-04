@app @details
Feature: Personal details
  As a candidate
  I want to manage contact information in the app shell
  So that my identity details stay consistent across CVs

  Background:
    Given the CV Studio app is running

  Scenario: Details page exposes identity and contact fields
    When I open the "personal details" page
    Then the response status is 200
    And the "details" nav item is marked active
    And the page heading contains "Personal details"
    And the page has an element matching "#first-name"
    And the page has an element matching "#email"
    And the page has an element matching "#save-details"
