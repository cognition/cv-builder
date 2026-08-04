@app @questions
Feature: Application questions
  As a candidate
  I want to capture questionnaires and link snippet evidence
  So that I can draft evidence-backed answers

  Background:
    Given the CV Studio app is running

  Scenario: Questions page is part of the shipped shell
    When I open the "questions" page
    Then the response status is 200
    And the "questions" nav item is marked active
    And the page heading contains "Application questions"
    And the page has an element matching "#source-list"
    And the page has an element matching "#question-list"

  Scenario: Question sources can be created and listed via the API
    When I create a question source via the API
    Then the response status is 201
    And the question sources list includes the created source
    And the questions list is non-empty
