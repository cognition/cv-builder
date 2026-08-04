@wireframe @library
Feature: Content library
  As a candidate
  I want to browse reusable career snippets at multiple detail levels
  So that I can reuse evidence across tailored CVs

  Background:
    Given the wireframe is loaded
    When I open the "library" view

  Scenario: Library shows snippet cards with detail levels
    Then I see a "Content library" heading
    And I see a search field for snippets
    And I see at least 1 snippet card
    And each visible snippet card offers Brief, Standard, and Detailed levels

  Scenario: Switching a snippet's detail level updates the copy
    When I open the first snippet card's "brief" level
    Then that snippet card shows the brief copy
    When I open the first snippet card's "detailed" level
    Then that snippet card shows the detailed copy

  Scenario: Creating a new snippet is available
    Then I see a primary action labelled "+ New snippet"
