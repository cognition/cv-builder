@wireframe @home
Feature: Home dashboard
  As a candidate
  I want a landing page that summarises my workspace
  So that I can pick up a tailored CV or start a new one

  Background:
    Given the wireframe is loaded
    When I open the "home" view

  Scenario: Home shows the tailor call to action
    Then I see a primary action labelled "Tailor a new CV"
    And I see a heading about building a focused CV

  Scenario: Home lists recent versions
    Then I see a "Recent versions" section
    And I see at least 1 version card

  Scenario: Home shows workspace stats
    Then I see a statistic for "Library snippets"
    And I see a statistic for "CV versions"

  Scenario: Tailor CTA opens the tailor flow
    When I click the primary action "Tailor a new CV"
    Then the "tailor" view is active
