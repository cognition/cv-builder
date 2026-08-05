@wireframe @details @track_b
Feature: Personal details
  As a candidate
  I want to manage identity, contact, and social profiles
  So that each CV version can show the right contact details

  Background:
    Given the wireframe is loaded
    When I open the "personal-details" view

  Scenario: Identity and contact fields are editable
    Then I see fields for first name, last name, and professional headline
    And I see contact fields for email and phone
    And I see a live preview of the contact block

  Scenario: Live preview updates when identity changes
    When I set the first name to "Alex"
    Then the live preview shows the first name "Alex"

  Scenario: Social profiles can be added and removed
    When I add a social profile
    Then a new profile row appears
    When I remove the last social profile
    Then that profile row is gone

  Scenario: Saving details confirms persistence
    When I save personal details
    Then I see a confirmation toast
