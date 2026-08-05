@wireframe @import @track_b
Feature: Import a resume
  As a candidate
  I want to bring an existing resume into CV Studio
  So that I can turn it into editable, reusable content

  Background:
    Given the wireframe is loaded
    When I open the "resume-import" view

  Scenario: Import starts at file selection
    Then I see an "Import a resume" heading
    And the import wizard shows step 1 as current
    And I see a drop zone for resume files
    And I can choose an import mode of new master CV, library, or compare

  Scenario: Choosing a resume advances through extraction
    When I choose a sample resume file named "sample-resume.pdf"
    Then the import processing stage becomes active
    And eventually the import review stage is shown
    And I see extracted sections for Profile, Work experience, Skills, and Education

  Scenario: Completing an import confirms selected content
    Given I have a resume ready to review
    When I import the selected content
    Then I see a confirmation toast
