// src/ui/static/script.js

document.addEventListener('DOMContentLoaded', () => {
    const shopifyForm = document.getElementById('shopify-form');
    const shopifyInput = document.getElementById('shop-domain');
    const shopifyConnectBtn = document.getElementById('shopify-connect-btn');
    const shopifyStep = document.getElementById('step-shopify');
    
    const metaStep = document.getElementById('step-meta');
    const metaConnectBtn = document.getElementById('meta-connect-btn');

    const successStep = document.getElementById('step-success');

    const statusArea = document.getElementById('status-area');

    // Get URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const status = urlParams.get('status');
    const tenantId = urlParams.get('tenant_id');
    const error = urlParams.get('error');

    // Display error if present
    if (error) {
        showStatus(error, 'error');
    }

    // Handle "Shopify Success" state
    if (status === 'shopify_success' && tenantId) {
        shopifyStep.classList.add('hidden');
        metaStep.classList.remove('hidden');
        showStatus('Shopify connected! Now connect Meta.', 'success');
        
        // Update Meta button link
        // We fetch the initiation URL from our backend to keep logic there
        // Or simply construct it if we know the endpoint pattern.
        // Let's construct it for simplicity, matching our API design.
        metaConnectBtn.href = `/api/auth/meta/initiate/${tenantId}`;
    }

    // Handle "Meta Success" state (Final step)
    if (status === 'meta_success' && tenantId) {
        shopifyStep.classList.add('hidden');
        metaStep.classList.add('hidden');
        successStep.classList.remove('hidden');
        showStatus('All accounts connected successfully!', 'success');
    }


    // Handle Shopify Form Submission
    shopifyForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const shop = shopifyInput.value.trim();
        
        if (!shop) {
            showStatus('Please enter your Shopify store domain.', 'error');
            return;
        }

        shopifyConnectBtn.disabled = true;
        shopifyConnectBtn.textContent = 'Connecting...';

        try {
            // Call backend to create tenant and get redirect URL
            const response = await fetch('/onboarding/initiate-shopify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ shopify_store_url: shop })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Failed to initiate connection');
            }

            const data = await response.json();
            
            // Redirect user to Shopify OAuth
            if (data.redirect_url) {
                window.location.href = data.redirect_url;
            } else {
                throw new Error('No redirect URL received');
            }

        } catch (err) {
            console.error(err);
            showStatus(err.message, 'error');
            shopifyConnectBtn.disabled = false;
            shopifyConnectBtn.textContent = 'Connect Shopify';
        }
    });

    function showStatus(message, type) {
        statusArea.textContent = message;
        statusArea.className = `status-message ${type}`;
        statusArea.style.display = 'block';
    }
});
