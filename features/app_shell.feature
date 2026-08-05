@app @shell
Feature: Real CV Studio app shell routes
  As a candidate using the shipped app
  I want every primary destination reachable
  So that navigation lands on live pages backed by real data

  Scenario Outline: Primary routes are reachable
    When I request the app path "<path>"
    Then the response status is 200
    And the page contains the app shell navigation
    And the "<active>" nav item is marked active

    Examples:
      | path              | active    |
      | /          | home      |
      | /details   | details   |
      | /import    | import    |
      | /build     | tailor    |
      | /questions | questions |
      | /library   | library   |
      | /variants  | versions  |
      | /assets    | assets    |
      | /connect   | connect   |

  Scenario: Master CV editor remains reachable
    When I request the app path "/edit"
    Then the response status is 200
    And the Master CV editor document is present

  Scenario: Wireframe prototype remains available as design reference only
    When I request the app path "/wireframe"
    Then the response status is 200
    And the page notes that it is sample data only
