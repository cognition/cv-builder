@app @questions
Feature: Application questions
  As a candidate
  I want to answer job requirements with linked evidence
  So that screening answers stay consistent with my CV library

  Background:
    Given the CV Studio app is running

  Scenario: Questions page summarises the workspace chrome
    When I open the "questions" page
    Then the response status is 200
    And the "questions" nav item is marked active
    And the page heading contains "Application questions"
    And the page has an element matching "#stat-total"
    And the page has an element matching "#stat-complete"
    And the page has an element matching "#stat-needs"
    And the page has an element matching "#source-list"
    And the page has an element matching "#question-list"
    And the page has an element matching "#answer-editor"
    And the page contains "Job description"
    And the page contains "Questionnaire"
    And the page contains "Competency matrix"

  Scenario: Question sources can be created and listed via the API
    When I create a question source via the API
    Then the response status is 201
    And the question sources list includes the created source
    And the questions list is non-empty

  @wip
  Scenario: Browser UI filters questions and links evidence
    # Requires driving questions.js selection, filters, and evidence picker.
    When I open the "questions" page
    Then the page has an element matching "#link-evidence"
