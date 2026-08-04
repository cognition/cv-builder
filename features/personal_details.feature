@app @details
Feature: Personal details
  As a candidate
  I want to manage identity, contact, and social profiles
  So that each CV version can show the right contact details

  Background:
    Given the CV Studio app is running

  Scenario: Identity and contact fields are present
    When I open the "personal details" page
    Then the response status is 200
    And the "details" nav item is marked active
    And the page heading contains "Personal details"
    And the page has an element matching "#first-name"
    And the page has an element matching "#last-name"
    And the page has an element matching "#headline"
    And the page has an element matching "#email"
    And the page has an element matching "#phone"
    And the page has an element matching "#save-details"
    And the page has an element matching ".details-preview"

  Scenario: Social profile controls are available
    When I open the "personal details" page
    Then the page has an element matching "#add-profile"
    And the page has an element matching "#profile-list"

  @wip
  Scenario: Live preview updates when identity changes
    # Requires browser JS against the shipped details page.
    When I open the "personal details" page
    Then the page contains "live preview"

  @wip
  Scenario: Saving details confirms persistence
    # Requires browser JS + save round-trip toast.
    When I open the "personal details" page
    Then the page has an element matching "#save-details"
