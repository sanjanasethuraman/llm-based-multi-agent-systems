import { useCallback, useMemo, useState } from 'react';

/**
 * Hook for managing multiple workflow tabs
 * Each workflow can be independently edited and executed
 */
export function useWorkflowTabs(defaultWorkflow) {
  const [tabs, setTabs] = useState([
    {
      id: 'workflow-1',
      name: 'Workflow 1',
      workflow: defaultWorkflow,
      createdAt: Date.now(),
      lastModified: Date.now(),
    },
  ]);
  const [activeTabId, setActiveTabId] = useState('workflow-1');

  const activeTab = useMemo(() => tabs.find((tab) => tab.id === activeTabId), [activeTabId, tabs]);

  const createTab = useCallback((name = null) => {
    const newId = `workflow-${Date.now()}`;
    const tabName = typeof name === 'string' && name.trim()
      ? name.trim()
      : `Workflow ${tabs.length + 1}`;
    const newTab = {
      id: newId,
      name: tabName,
      workflow: defaultWorkflow,
      createdAt: Date.now(),
      lastModified: Date.now(),
      executionMode: 'independent', // independent, sequential, parallel
      executionResults: null,
    };
    setTabs((current) => [...current, newTab]);
    setActiveTabId(newId);
    return newId;
  }, [tabs.length, defaultWorkflow]);

  const duplicateTab = useCallback((sourceTabId) => {
    const sourceTab = tabs.find((t) => t.id === sourceTabId);
    if (!sourceTab) return null;

    const newId = `workflow-${Date.now()}`;
    const newTab = {
      ...sourceTab,
      id: newId,
      name: `${sourceTab.name} (Copy)`,
      createdAt: Date.now(),
      lastModified: Date.now(),
      executionResults: null, // Clear previous results
    };
    setTabs((current) => [...current, newTab]);
    setActiveTabId(newId);
    return newId;
  }, [tabs]);

  const updateTab = useCallback((tabId, updates) => {
    setTabs((current) =>
      current.map((tab) =>
        tab.id === tabId
          ? {
              ...tab,
              ...updates,
              lastModified: Date.now(),
            }
          : tab
      )
    );
  }, []);

  const updateTabWorkflow = useCallback((tabId, workflow) => {
    updateTab(tabId, { workflow });
  }, [updateTab]);

  const updateTabExecutionMode = useCallback((tabId, mode) => {
    if (!['independent', 'sequential', 'parallel'].includes(mode)) {
      throw new Error(`Invalid execution mode: ${mode}`);
    }
    updateTab(tabId, { executionMode: mode });
  }, [updateTab]);

  const setTabExecutionResults = useCallback((tabId, results) => {
    updateTab(tabId, { executionResults: results });
  }, [updateTab]);

  const closeTab = useCallback((tabId) => {
    if (tabs.length === 1) {
      return false;
    }
    setTabs((current) => current.filter((tab) => tab.id !== tabId));
    if (activeTabId === tabId) {
      setActiveTabId((current) => {
        const remaining = tabs.filter((tab) => tab.id !== tabId);
        return remaining[remaining.length - 1]?.id || 'workflow-1';
      });
    }
    return true;
  }, [tabs, activeTabId]);

  const renameTab = useCallback((tabId, newName) => {
    updateTab(tabId, { name: newName });
  }, [updateTab]);

  return {
    tabs,
    activeTabId,
    activeTab,
    createTab,
    duplicateTab,
    updateTabWorkflow,
    updateTabExecutionMode,
    setTabExecutionResults,
    closeTab,
    renameTab,
    setActiveTabId,
  };
}
