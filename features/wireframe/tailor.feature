@wireframe @tailor
Feature: Tailor a CV to a job posting
  As a candidate
  I want to paste a job posting and choose matching evidence
  So that I can export a focused application CV

  Background:
    Given the wireframe is loaded

  Scenario: Step 1 collects job details
    When I open the "tailor" view
    Then the tailor wizard shows step 1 as current
    And I see a field for the version name
    And I see a job posting textarea
    And I see a primary action labelled "Analyze job posting"

  Scenario: Analyzing a posting moves to content selection
    When I open the "tailor" view
    And I paste a job posting about "cloud platforms" and "cross-functional teams"
    And I analyze the job posting
    Then the "match" view is active
    And the tailor wizard shows step 2 as current
    And I see suggested content to select

  Scenario: Selecting content and reviewing the draft
    Given I have analyzed a sample job posting
    When I select at least 1 suggested snippet
    And I review the draft
    Then the "review" view is active
    And the tailor wizard shows step 3 as current
    And I see a document outline
    And I see a primary action labelled "Export PDF"

  Scenario: Saving and exporting from review
    Given I am on the review step of the tailor flow
    When I save the version
    Then I see a confirmation toast
    When I export the PDF
    Then I see a confirmation toast
