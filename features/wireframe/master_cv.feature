@wireframe @master
Feature: Master CV
  As a candidate
  I want a complete source CV
  So that tailored versions can start from a single foundation

  Background:
    Given the wireframe is loaded
    When I open the "master" view

  Scenario: Master CV invites the user to open the source document
    Then I see a "master CV" heading
    And I see a primary action labelled "Open master CV"

  Scenario: Opening the master CV enters a reviewable document
    When I click the primary action "Open master CV"
    Then the "review" view is active
