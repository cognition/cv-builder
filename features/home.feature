@app @home
Feature: Home dashboard
  As a candidate
  I want a landing page that summarises my workspace
  So that I can pick up a tailored CV or start a new one

  Background:
    Given the CV Studio app is running

  Scenario: Home shows the tailor call to action
    When I open the "home" page
    Then the response status is 200
    And the page heading contains "Build a focused CV"
    And the page contains "Tailor a new CV"
    And the page has an element matching "a.primary[href='/build']"

  Scenario: Home lists recent versions
    When I open the "home" page
    Then the page heading contains "Recent versions"
    And the page has an element matching "a[href='/variants']"

  Scenario: Home shows workspace stats
    When I open the "home" page
    Then the home page reports a snippet count
    And the home page reports a versions count
