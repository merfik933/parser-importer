add_action('rest_api_init', function () {
    register_rest_route('custom/v1', '/set-color-meta/', array(
        'methods' => 'POST',
        'callback' => 'set_color_meta_callback',
        'permission_callback' => function () {
            return current_user_can('edit_products');
        }
    ));
});

function set_color_meta_callback($request) {
    $term_id = $request->get_param('term_id');
    $hex = $request->get_param('hex');

    if (!$term_id || !$hex) {
        return new WP_Error('missing_data', 'Missing term_id or hex', array('status' => 400));
    }

    update_term_meta($term_id, '_wcboost_variation_swatches_color', $hex);
    update_term_meta($term_id, 'swatches_color', $hex); // ← Додано

    $result = [
        'term_id' => $term_id,
        'requested_hex' => $hex,
        'read_back_wcboost' => get_term_meta($term_id, '_wcboost_variation_swatches_color', true),
        'read_back_main' => get_term_meta($term_id, 'swatches_color', true),
        'all_meta' => get_term_meta($term_id)
    ];

    return $result;
}