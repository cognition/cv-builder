@wireframe @assets
Feature: Asset library
  As a candidate
  I want to manage photos, logos, and contact icons
  So that I can reuse visual identity across CVs

  Background:
    Given the wireframe is loaded
    When I open the "assets" view

  Scenario: Assets page summarises the library
    Then I see an "Asset library" heading
    And I see filter tabs for All, Photos, Logos, and Contact icons
    And I see a search field for assets

  Scenario: Selecting an asset opens the inspector
    When I select the asset named "LinkedIn"
    Then the asset inspector shows "LinkedIn"
    And I see a primary action labelled "Use this asset"

  Scenario: Adding an asset opens the upload modal
    When I click the primary action "+ Add asset"
    Then the add-asset modal is visible
    And I can choose upload or URL as the source
