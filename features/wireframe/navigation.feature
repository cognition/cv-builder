@wireframe @shell
Feature: CV Studio navigation shell
  As a candidate using CV Studio
  I want a persistent left-hand navigation
  So that I can move between the main areas of the product

  Background:
    Given the wireframe is loaded

  Scenario: The shell exposes every primary destination
    Then the navigation lists the following destinations:
      | destination       |
      | Home              |
      | Master CV         |
      | Personal details  |
      | Import resume     |
      | Tailor            |
      | Questions         |
      | Content library   |
      | Assets            |
      | Versions          |
      | Connect AI        |

  Scenario Outline: Opening a view updates the main content
    When I open the "<view>" view
    Then the "<view>" view is active
    And the page title contains "<title_fragment>"

    Examples:
      | view             | title_fragment   |
      | home             | Good morning     |
      | tailor           | Tell us about    |
      | library          | career content   |
      | versions         | Application-ready |
      | assets           | visual identity  |
      | personal-details | Personal and     |
      | resume-import    | existing resume  |
      | questions        | evidence-backed  |
      | mcp              | assistant        |
      | master           | source of truth  |

  Scenario: The brand link returns to Home
    When I open the "library" view
    And I click the brand link
    Then the "home" view is active
