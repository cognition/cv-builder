@app @assets
Feature: Asset library
  As a candidate
  I want to manage photos, logos, and contact icons
  So that I can reuse visual identity across CVs

  Background:
    Given the CV Studio app is running

  Scenario: Assets page summarises the library chrome
    When I open the "assets" page
    Then the response status is 200
    And the "assets" nav item is marked active
    And the page heading contains "Asset library"
    And the page has an element matching "#personal-assets"
    And the page has an element matching "#icon-assets"
    And the page has an element matching "#asset-search"
    And the page has an element matching "[data-asset-filter='all']"
    And the page has an element matching "[data-asset-filter='photo']"
    And the page has an element matching "#upload-trigger"

  Scenario: Images API is reachable
    When I GET the API path "/api/images"
    Then the response status is 200
    And the JSON response is a list

  @wip
  Scenario: Browser UI opens the asset inspector and add-asset flow
    # Requires driving assets.js selection and modal.
    When I open the "assets" page
    Then the page has an element matching "#inspector-empty"
