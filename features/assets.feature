@app @assets
Feature: Asset library
  As a candidate
  I want to manage photos and icons in the app
  So that I can reuse visual assets on my CV

  Background:
    Given the CV Studio app is running

  Scenario: Assets page lists personal and built-in icons
    When I open the "assets" page
    Then the response status is 200
    And the "assets" nav item is marked active
    And the page heading contains "Asset library"
    And the page has an element matching "#personal-assets"
    And the page has an element matching "#icon-assets"

  Scenario: Images API is reachable
    When I GET the API path "/api/images"
    Then the response status is 200
    And the JSON response is a list
