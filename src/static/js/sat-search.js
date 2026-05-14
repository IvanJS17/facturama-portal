/**
 * SAT Catalog Search Component
 * Provides searchable dropdowns for SAT catalogs (ClaveProdServ, ClaveUnidad, etc.)
 */

class SATSearchSelect {
    constructor(inputElement, options = {}) {
        this.input = inputElement;
        this.options = {
            apiUrl: options.apiUrl || '',
            placeholder: options.placeholder || 'Buscar...',
            minChars: options.minChars || 2,
            maxResults: options.maxResults || 20,
            onSelect: options.onSelect || null,
            displayField: options.displayField || 'description',
            valueField: options.valueField || 'code',
            formatResult: options.formatResult || null,
            ...options
        };
        
        this.dropdown = null;
        this.results = [];
        this.selectedIndex = -1;
        this.isOpen = false;
        this.debounceTimer = null;
        
        this.init();
    }
    
    init() {
        // Create wrapper
        this.wrapper = document.createElement('div');
        this.wrapper.className = 'sat-search-wrapper';
        this.input.parentNode.insertBefore(this.wrapper, this.input);
        this.wrapper.appendChild(this.input);
        
        // Create dropdown
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'sat-search-dropdown';
        this.dropdown.style.display = 'none';
        this.wrapper.appendChild(this.dropdown);
        
        // Add event listeners
        this.input.addEventListener('input', () => this.onInput());
        this.input.addEventListener('keydown', (e) => this.onKeydown(e));
        this.input.addEventListener('focus', () => this.onFocus());
        document.addEventListener('click', (e) => this.onClickOutside(e));
        
        // Style the input
        this.input.classList.add('sat-search-input');
        this.input.setAttribute('autocomplete', 'off');
        this.input.setAttribute('placeholder', this.options.placeholder);
    }
    
    onInput() {
        clearTimeout(this.debounceTimer);
        const query = this.input.value.trim();
        
        if (query.length < this.options.minChars) {
            this.close();
            return;
        }
        
        this.debounceTimer = setTimeout(() => {
            this.search(query);
        }, 300);
    }
    
    onKeydown(e) {
        if (!this.isOpen) return;
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectedIndex = Math.min(this.selectedIndex + 1, this.results.length - 1);
                this.highlightSelected();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
                this.highlightSelected();
                break;
            case 'Enter':
                e.preventDefault();
                if (this.selectedIndex >= 0 && this.selectedIndex < this.results.length) {
                    this.selectResult(this.results[this.selectedIndex]);
                }
                break;
            case 'Escape':
                this.close();
                break;
        }
    }
    
    onFocus() {
        const query = this.input.value.trim();
        if (query.length >= this.options.minChars) {
            this.search(query);
        }
    }
    
    onClickOutside(e) {
        if (!this.wrapper.contains(e.target)) {
            this.close();
        }
    }
    
    async search(query) {
        try {
            const response = await fetch(`${this.options.apiUrl}?q=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error('Search failed');
            
            this.results = await response.json();
            this.selectedIndex = -1;
            this.showResults();
        } catch (error) {
            console.error('SAT search error:', error);
            this.close();
        }
    }
    
    showResults() {
        this.dropdown.innerHTML = '';
        
        if (this.results.length === 0) {
            this.dropdown.innerHTML = '<div class="sat-search-no-results">No se encontraron resultados</div>';
            this.open();
            return;
        }
        
        this.results.forEach((result, index) => {
            const item = document.createElement('div');
            item.className = 'sat-search-item';
            item.dataset.index = index;
            
            if (this.options.formatResult) {
                item.innerHTML = this.options.formatResult(result);
            } else {
                const code = result[this.options.valueField] || '';
                const desc = result[this.options.displayField] || '';
                item.innerHTML = `<strong>${this.escapeHtml(code)}</strong> - ${this.escapeHtml(desc)}`;
            }
            
            item.addEventListener('click', () => this.selectResult(result));
            item.addEventListener('mouseenter', () => {
                this.selectedIndex = index;
                this.highlightSelected();
            });
            
            this.dropdown.appendChild(item);
        });
        
        this.open();
    }
    
    highlightSelected() {
        const items = this.dropdown.querySelectorAll('.sat-search-item');
        items.forEach((item, index) => {
            item.classList.toggle('selected', index === this.selectedIndex);
        });
        
        // Scroll into view
        if (this.selectedIndex >= 0 && items[this.selectedIndex]) {
            items[this.selectedIndex].scrollIntoView({ block: 'nearest' });
        }
    }
    
    selectResult(result) {
        const code = result[this.options.valueField] || '';
        const desc = result[this.options.displayField] || '';
        
        this.input.value = `${code} - ${desc}`;
        this.input.dataset.value = code;
        
        if (this.options.onSelect) {
            this.options.onSelect(result);
        }
        
        this.close();
    }
    
    open() {
        this.dropdown.style.display = 'block';
        this.isOpen = true;
    }
    
    close() {
        this.dropdown.style.display = 'none';
        this.isOpen = false;
        this.selectedIndex = -1;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    getValue() {
        return this.input.dataset.value || this.input.value;
    }
    
    setValue(code, displayText = '') {
        this.input.dataset.value = code;
        if (displayText) {
            this.input.value = `${code} - ${displayText}`;
        }
    }
}

// Auto-initialize SAT search selects
document.addEventListener('DOMContentLoaded', function() {
    // Find all elements with data-sat-search attribute
    document.querySelectorAll('[data-sat-search]').forEach(input => {
        const type = input.dataset.satSearch;
        const apiUrl = `/api/sat/${type}/search`;
        
        new SATSearchSelect(input, {
            apiUrl: apiUrl,
            placeholder: input.dataset.placeholder || 'Buscar...',
            minChars: parseInt(input.dataset.minChars) || 2,
            onSelect: input.dataset.onSelect ? eval(`(${input.dataset.onSelect})`) : null
        });
    });
});
