@wireframe @versions
Feature: CV versions
  As a candidate
  I want to see drafts and exported application documents
  So that I can reopen or continue a tailored CV

  Background:
    Given the wireframe is loaded
    When I open the "versions" view

  Scenario: Versions list shows status and open actions
    Then I see a "CV versions" heading
    And I see at least 1 version row
    And I see a status pill of "READY" or "DRAFT"
    And each version row has an "Open" action

  Scenario: Starting a new tailored CV from versions
    When I click the primary action "+ New tailored CV"
    Then the "tailor" view is active
