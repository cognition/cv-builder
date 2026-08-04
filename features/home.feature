@app @home
Feature: Home dashboard
  As a candidate
  I want a live workspace dashboard
  So that I can jump into Tailor and see library/version counts

  Background:
    Given the CV Studio app is running

  Scenario: Home introduces the product and primary CTA
    When I open the "home" page
    Then the response status is 200
    And the page heading contains "Build a focused CV"
    And the page contains "Tailor a new CV"
    And the page has an element matching "a.primary[href='/cv/web/build']"
    And the home page reports a snippet count

  Scenario: Home links to the versions list
    When I open the "home" page
    Then the page has an element matching "a[href='/cv/web/variants']"
