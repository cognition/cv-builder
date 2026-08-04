@wireframe @questions @track_b
Feature: Application questions
  As a candidate
  I want to answer job requirements with linked evidence
  So that screening answers stay consistent with my CV library

  Background:
    Given the wireframe is loaded
    When I open the "questions" view

  Scenario: Questions dashboard summarises progress
    Then I see an "Application questions" heading
    And I see totals for answered, needs evidence, and not started
    And I see a list of question sources

  Scenario: Selecting a question opens the answer workspace
    When I select the first open question
    Then the answer workspace shows that question's title
    And I can edit the answer text
    And I can link evidence from the library

  Scenario: Filtering questions by status
    When I filter questions to "Needs work"
    Then every visible question row needs work
    When I filter questions to "Complete"
    Then every visible question row is complete

  Scenario: Adding a question source
    When I start adding a question source
    Then I can choose Job description, Questionnaire, or Competency matrix
