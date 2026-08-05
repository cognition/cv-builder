@app @shell
Feature: CV Studio navigation shell
  As a candidate using CV Studio
  I want a persistent left-hand navigation
  So that I can move between the main areas of the product

  # Informed by the wireframe shell; asserted against the shipped app.

  Background:
    Given the CV Studio app is running

  Scenario: The shell exposes every primary destination
    When I open the "home" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the navigation lists the following destinations:
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

  Scenario Outline: Opening a shell page marks the correct nav item
    When I open the "<page>" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the "<active>" nav item is marked active
    And the page title contains "<title_fragment>"

    Examples:
      | page              | active    | title_fragment   |
      | home              | home      | Home             |
      | personal details  | details   | Personal details |
      | import resume     | import    | Import           |
      | tailor            | tailor    | Tailor           |
      | questions         | questions | Questions        |
      | content library   | library   | Content library  |
      | assets            | assets    | Assets           |
      | versions          | versions  | Versions         |
      | connect ai        | connect   | Connect AI       |

  Scenario: The brand link points home
    When I open the "content library" page
    Then the page has an element matching "a.brand[href='/']"
