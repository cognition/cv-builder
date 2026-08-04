@app @shell
Feature: Real CV Studio app shell
  As a candidate using the shipped app (not the sample wireframe)
  I want the wireframe destinations that already exist
  So that navigation lands on live pages backed by real data

  Scenario Outline: Track A routes are reachable
    When I request the app path "<path>"
    Then the response status is 200
    And the page contains the app shell navigation
    And the "<active>" nav item is marked active

    Examples:
      | path             | active    |
      | /cv/web/         | home      |
      | /cv/web/details  | details   |
      | /cv/web/import   | import    |
      | /cv/web/build    | tailor    |
      | /cv/web/questions| questions |
      | /cv/web/library  | library   |
      | /cv/web/variants | versions  |
      | /cv/web/assets   | assets    |
      | /cv/web/connect  | connect   |

  Scenario: Master CV editor remains reachable
    When I request the app path "/cv/web/edit"
    Then the response status is 200

  Scenario: Wireframe prototype remains available as a reference
    When I request the app path "/cv/web/wireframe"
    Then the response status is 200
    And the page notes that it is sample data only
