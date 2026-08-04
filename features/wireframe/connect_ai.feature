@wireframe @connect
Feature: Connect AI (MCP)
  As a candidate
  I want to connect an AI assistant to my local CV library
  So that I can search, match, and compose CVs from a chat client

  Background:
    Given the wireframe is loaded
    When I open the "mcp" view

  Scenario: Connect AI explains the integration
    Then I see a heading about using the CV library from an AI assistant
    And I see a three-step setup guide
    And I see a copyable docker compose command
    And I see an example assistant prompt

  Scenario: Testing the MCP connection
    When I test the MCP connection
    Then I see a connection test result
