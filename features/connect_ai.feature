@app @connect
Feature: Connect AI (MCP)
  As a candidate
  I want setup guidance for connecting an assistant
  So that I can use my library from MCP-capable tools

  Background:
    Given the CV Studio app is running

  Scenario: Connect page explains local MCP setup
    When I open the "connect ai" page
    Then the response status is 200
    And the "connect" nav item is marked active
    And the page heading contains "Use your CV library"
    And the page contains "MCP"
    And the page contains "docker compose up"
